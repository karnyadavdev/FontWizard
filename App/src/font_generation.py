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

    font["OS/2"].version = identity["os2_version"]
    font["OS/2"].usWeightClass = identity["os2_weight"]
    font["OS/2"].usWidthClass = identity["os2_width"]
    font["OS/2"].fsSelection = identity["os2_fsSelection"]

    if identity["os2_panose"] is not None:
        font["OS/2"].panose = identity["os2_panose"]

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
    source_path = Path(source_path)
    segoe_var_path = Path(segoe_var_path)
    output_path = Path(output_path)
    
    if not source_path.exists():
        raise FileNotFoundError(f"Font not found: {source_path}")
    if not segoe_var_path.exists():
        raise FileNotFoundError(f"System variable font not found: {segoe_var_path}")


    donor = None
    source = None
    try:
        donor = TTFont(segoe_var_path)
        source = TTFont(source_path)
        donor.sfntVersion = source.sfntVersion

        tables_to_swap = [
            "glyf", "loca", "hmtx", "maxp", "cmap", "post",
            "prep", "fpgm", "cvt ", "gasp",
            "GSUB", "GPOS", "GDEF",
            "kern", "vmtx", "vhea",
            "math", "BASE", "JSTF",
            "hdmx", "LTSH", "VDMX", "PCLT",
        ]

        for tag in tables_to_swap:
            if tag in source:
                donor[tag] = source[tag]
            elif tag in donor:
                del donor[tag]

        donor.setGlyphOrder(source.getGlyphOrder())

        for attr in ("xMin", "yMin", "xMax", "yMax", "unitsPerEm"):
            setattr(donor["head"], attr, getattr(source["head"], attr))

        donor["hhea"].ascent = source["hhea"].ascent
        donor["hhea"].descent = source["hhea"].descent
        donor["hhea"].lineGap = source["hhea"].lineGap
        donor["hhea"].numberOfHMetrics = source["hhea"].numberOfHMetrics

        for attr in ("sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent", "usWinDescent"):
            setattr(donor["OS/2"], attr, getattr(source["OS/2"], attr))

        for tag in ("gvar", "cvar", "MVAR", "HVAR", "VVAR", "avar", "DSIG"):
            if tag in donor:
                del donor[tag]

        donor.save(output_path)
    finally:
        if donor is not None:
            donor.close()
        if source is not None:
            source.close()

    return output_path
