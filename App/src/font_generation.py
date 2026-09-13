from pathlib import Path

from fontTools.ttLib import TTFont


def read_segoe_identity(segoe_path):
    font = TTFont(segoe_path)
    try:
        identity = {
            "macStyle": font["head"].macStyle,
            "os2_version": font["OS/2"].version,
            "os2_weight": font["OS/2"].usWeightClass,
            "os2_width": font["OS/2"].usWidthClass,
            "os2_fsSelection": font["OS/2"].fsSelection,
            "post_italicAngle": font["post"].italicAngle,
            "name_records": [],
        }

        try:
            identity["os2_panose"] = font["OS/2"].panose
        except AttributeError:
            identity["os2_panose"] = None

        for record in font["name"].names:
            try:
                identity["name_records"].append(
                    {
                        "nameID": record.nameID,
                        "platformID": record.platformID,
                        "platEncID": record.platEncID,
                        "langID": record.langID,
                        "string": record.toUnicode(),
                    }
                )
            except UnicodeDecodeError:
                continue

        return identity
    finally:
        font.close()


def apply_identity(font, identity):
    kept_names = []
    if "fvar" in font:
        kept_names = [n for n in font["name"].names if n.nameID > 255]
    
    font["name"].names = kept_names
    for record in identity["name_records"]:
        font["name"].setName(
            record["string"],
            record["nameID"],
            record["platformID"],
            record["platEncID"],
            record["langID"],
        )

    target_os2_version = identity["os2_version"]
    os2 = font["OS/2"]

    if target_os2_version >= 1:
        if not hasattr(os2, "ulCodePageRange1"):
            os2.ulCodePageRange1 = 0
        if not hasattr(os2, "ulCodePageRange2"):
            os2.ulCodePageRange2 = 0

    if target_os2_version >= 2:
        upem = font["head"].unitsPerEm if "head" in font else 2048
        if not hasattr(os2, "sxHeight") or os2.sxHeight is None:
            try:
                glyf = font["glyf"]
                if "x" in glyf and glyf["x"].numberOfContours != 0:
                    os2.sxHeight = glyf["x"].yMax
                else:
                    os2.sxHeight = int(upem * 0.5)
            except Exception:
                os2.sxHeight = int(upem * 0.5)

        if not hasattr(os2, "sCapHeight") or os2.sCapHeight is None:
            try:
                glyf = font["glyf"]
                if "H" in glyf and glyf["H"].numberOfContours != 0:
                    os2.sCapHeight = glyf["H"].yMax
                else:
                    os2.sCapHeight = int(upem * 0.7)
            except Exception:
                os2.sCapHeight = int(upem * 0.7)

        if not hasattr(os2, "usDefaultChar"):
            os2.usDefaultChar = 0
        if not hasattr(os2, "usBreakChar"):
            os2.usBreakChar = 32
        if not hasattr(os2, "usMaxContext"):
            os2.usMaxContext = 1

    if target_os2_version >= 5:
        if not hasattr(os2, "usLowerOpticalPointSize"):
            os2.usLowerOpticalPointSize = 0
        if not hasattr(os2, "usUpperOpticalPointSize"):
            os2.usUpperOpticalPointSize = 0xFFFF / 20

    os2.version = target_os2_version
    os2.usWeightClass = identity["os2_weight"]
    os2.usWidthClass = identity["os2_width"]
    os2.fsSelection = identity["os2_fsSelection"]

    if identity["os2_panose"] is not None:
        os2.panose = identity["os2_panose"]

    if "DSIG" in font:
        del font["DSIG"]

    font["head"].macStyle = identity["macStyle"]
    font["post"].italicAngle = identity["post_italicAngle"]


def build_font(source_path, segoe_path, output_path):
    source_path = Path(source_path)
    segoe_path = Path(segoe_path)
    output_path = Path(output_path)
    
    if not source_path.exists():
        raise FileNotFoundError(f"Font not found: {source_path}")
    if not segoe_path.exists():
        raise FileNotFoundError(f"System font not found: {segoe_path}")

    identity = read_segoe_identity(segoe_path)
    font = TTFont(source_path)
    try:
        apply_identity(font, identity)
        font.save(str(output_path))
    finally:
        font.close()

    return str(output_path)


def build_variable_font(source_path, segoe_var_path, output_path):
    """Build a clean static font containing Segoe UI Variable's identity.

    Tricking Windows 11 into using a user's static font when Segoe UI Variable is requested
    is achieved by generating a valid static TrueType font with Segoe UI Variable's name
    and OS/2 tables. Splicing partial variable tables without gvar is invalid per OpenType spec.
    """
    return build_font(source_path, segoe_var_path, output_path)

