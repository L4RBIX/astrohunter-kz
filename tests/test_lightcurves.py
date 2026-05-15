"""Tests for astrohunter.lightcurves — no network calls, no real TESS downloads."""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.lightcurves import (
    _format_download_error,
    estimate_noise_mad,
    lightcurve_to_dataframe,
    download_lightcurve_for_tic,
)


class MinimalLightCurve:
    def __init__(self):
        self.time = np.array([1.0, 2.0, 3.0, np.nan, 4.0])
        self.flux = np.array([1.0, 0.99, 1.01, 1.0, np.nan])
        self.flux_err = np.array([0.001, 0.001, 0.001, 0.001, 0.001])
        self.quality = np.array([0, 0, 1, 0, 0])


def test_estimate_noise_mad_returns_positive_value():
    rng = np.random.default_rng(123)
    flux = 1.0 + rng.normal(0, 0.001, size=500)

    noise = estimate_noise_mad(flux)

    assert np.isfinite(noise)
    assert noise > 0


def test_lightcurve_to_dataframe_with_minimal_object():
    df = lightcurve_to_dataframe(MinimalLightCurve())

    assert list(df.columns) == ["time_btjd", "flux", "flux_err", "quality"]
    assert len(df) == 3
    assert df["time_btjd"].tolist() == [1.0, 2.0, 3.0]


# ============================================================================
# _format_download_error
# ============================================================================

class TestFormatDownloadError:
    def test_returns_string(self):
        exc = RuntimeError("test error")
        result = _format_download_error(exc, tic_id=12345)
        assert isinstance(result, str)

    def test_includes_exception_class(self):
        exc = RuntimeError("something went wrong")
        result = _format_download_error(exc, tic_id=12345)
        assert "RuntimeError" in result

    def test_includes_exception_message(self):
        exc = RuntimeError("something went wrong")
        result = _format_download_error(exc, tic_id=12345)
        assert "something went wrong" in result

    def test_syntax_error_class_included(self):
        # SyntaxError is the real-world trigger (corrupted __init__.py)
        exc = SyntaxError("expected an indented block", ("__init__.py", 7, None, None))
        result = _format_download_error(exc, tic_id=99999)
        assert "SyntaxError" in result

    def test_indentation_error_class_included(self):
        exc = IndentationError("unexpected indent", ("prf/__init__.py", 7, 1, "    x\n"))
        result = _format_download_error(exc, tic_id=12345)
        assert "IndentationError" in result

    def test_value_error_class_included(self):
        exc = ValueError("bad value")
        result = _format_download_error(exc, tic_id=1)
        assert "ValueError" in result
        assert "bad value" in result

    def test_author_kwarg_accepted(self):
        exc = RuntimeError("timeout")
        result = _format_download_error(exc, tic_id=1, author="SPOC")
        assert isinstance(result, str)

    def test_format_is_classname_colon_message(self):
        exc = OSError("network unreachable")
        result = _format_download_error(exc, tic_id=1)
        assert result == "OSError: network unreachable"


# ============================================================================
# download_lightcurve_for_tic — failure paths (no network)
# ============================================================================

class TestDownloadLightcurveForTicFailures:
    def test_returns_none_when_lightkurve_raises_syntax_error(self):
        """SyntaxError during lightkurve import must be caught and return None."""
        with patch(
            "astrohunter.lightcurves.download_lightcurve_for_tic",
            wraps=download_lightcurve_for_tic,
        ):
            # Simulate broken lightkurve import by patching builtins.__import__
            original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

            def _bad_import(name, *args, **kwargs):
                if name == "lightkurve":
                    raise SyntaxError(
                        "expected an indented block",
                        ("prf/__init__.py", 7, None, None),
                    )
                return original_import(name, *args, **kwargs)

            import builtins
            with patch.object(builtins, "__import__", side_effect=_bad_import):
                result = download_lightcurve_for_tic(12345)
            assert result is None

    def test_returns_none_when_no_products_found(self):
        """Empty search result returns None gracefully."""
        mock_sr = MagicMock()
        mock_sr.__len__ = lambda self: 0
        mock_lk = MagicMock()
        mock_lk.search_lightcurve.return_value = mock_sr

        with patch.dict("sys.modules", {"lightkurve": mock_lk}):
            result = download_lightcurve_for_tic(99999)
        assert result is None

    def test_returns_none_when_download_raises(self):
        """Exception during download_all() is caught and returns None."""
        mock_sr = MagicMock()
        mock_sr.__len__ = lambda self: 1
        mock_sr.__getitem__ = MagicMock(return_value=mock_sr)
        mock_sr.download_all.side_effect = RuntimeError("download timed out")

        mock_lk = MagicMock()
        mock_lk.search_lightcurve.return_value = mock_sr

        with patch.dict("sys.modules", {"lightkurve": mock_lk}):
            result = download_lightcurve_for_tic(11111)
        assert result is None


# ============================================================================
# debug_lightcurve_download.py — argument parsing (no network)
# ============================================================================

class TestDebugScriptArgParsing:
    def _load_debug_module(self):
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        spec = importlib.util.spec_from_file_location(
            "debug_lightcurve_download",
            scripts_dir / "debug_lightcurve_download.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_tic_id_required(self):
        mod = self._load_debug_module()
        with pytest.raises(SystemExit):
            mod._parse_args([])

    def test_tic_id_parsed(self):
        mod = self._load_debug_module()
        args = mod._parse_args(["--tic-id", "368404959"])
        assert args.tic_id == 368404959

    def test_verbose_flag(self):
        mod = self._load_debug_module()
        args = mod._parse_args(["--tic-id", "1", "--verbose"])
        assert args.verbose is True

    def test_max_lightcurves_default(self):
        mod = self._load_debug_module()
        args = mod._parse_args(["--tic-id", "1"])
        assert args.max_lightcurves == 1

    def test_max_lightcurves_custom(self):
        mod = self._load_debug_module()
        args = mod._parse_args(["--tic-id", "1", "--max-lightcurves", "3"])
        assert args.max_lightcurves == 3

    def test_author_preference_default(self):
        mod = self._load_debug_module()
        args = mod._parse_args(["--tic-id", "1"])
        assert "SPOC" in args.author_preference
        assert "QLP" in args.author_preference

    def test_author_preference_custom(self):
        mod = self._load_debug_module()
        args = mod._parse_args(["--tic-id", "1", "--author-preference", "TESS-SPOC"])
        assert args.author_preference == ["TESS-SPOC"]
