from pathlib import Path
import struct
import unicodedata

from fontTools.ttLib import TTFont


def read_segoe_identity(segoe_path):
    font = TTFont(segoe_path)
    try:
        identity = {
            "macStyle": font["head"].macStyle,
            "unitsPerEm": getattr(font["head"], "unitsPerEm", 2048),
            "os2_version": font["OS/2"].version,
            "os2_weight": font["OS/2"].usWeightClass,
            "os2_width": font["OS/2"].usWidthClass,
            "os2_fsSelection": font["OS/2"].fsSelection,
            "post_italicAngle": font["post"].italicAngle,
            "name_records": [],
            "sTypoAscender": getattr(font["OS/2"], "sTypoAscender", None),
            "sTypoDescender": getattr(font["OS/2"], "sTypoDescender", None),
            "sTypoLineGap": getattr(font["OS/2"], "sTypoLineGap", 0),
            "usWinAscent": getattr(font["OS/2"], "usWinAscent", None),
            "usWinDescent": getattr(font["OS/2"], "usWinDescent", None),
            "hhea_ascent": getattr(font["hhea"], "ascent", None) if "hhea" in font else None,
            "hhea_descent": getattr(font["hhea"], "descent", None) if "hhea" in font else None,
            "hhea_lineGap": getattr(font["hhea"], "lineGap", 0) if "hhea" in font else 0,
        }

        try:
            identity["os2_panose"] = font["OS/2"].panose
        except AttributeError:
            identity["os2_panose"] = None

        if hasattr(font["OS/2"], "usLowerOpticalPointSize"):
            identity["usLowerOpticalPointSize"] = font["OS/2"].usLowerOpticalPointSize
        if hasattr(font["OS/2"], "usUpperOpticalPointSize"):
            identity["usUpperOpticalPointSize"] = font["OS/2"].usUpperOpticalPointSize

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
    if "fvar" not in font and "STAT" in font:
        del font["STAT"]

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
            os2.usLowerOpticalPointSize = identity.get("usLowerOpticalPointSize", 0)
        if not hasattr(os2, "usUpperOpticalPointSize"):
            os2.usUpperOpticalPointSize = identity.get("usUpperOpticalPointSize", 0xFFFF // 20)

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

    # Normalize vertical line metrics to match Segoe UI proportions (scaled to font UPM).
    # This prevents unwanted empty spacing above/below text in Google Sans, Product Sans, Inter, etc.
    donor_upm = identity.get("unitsPerEm", 2048) or 2048
    target_upm = getattr(font["head"], "unitsPerEm", 2048) if "head" in font else 2048
    scale = (target_upm / donor_upm) if (donor_upm and donor_upm != target_upm) else 1.0

    if identity.get("sTypoAscender") is not None:
        os2.sTypoAscender = int(round(identity["sTypoAscender"] * scale))
    if identity.get("sTypoDescender") is not None:
        os2.sTypoDescender = int(round(identity["sTypoDescender"] * scale))
    if identity.get("sTypoLineGap") is not None:
        os2.sTypoLineGap = int(round(identity["sTypoLineGap"] * scale))
    if identity.get("usWinAscent") is not None:
        os2.usWinAscent = int(round(identity["usWinAscent"] * scale))
    if identity.get("usWinDescent") is not None:
        os2.usWinDescent = int(round(identity["usWinDescent"] * scale))

    if "hhea" in font:
        if identity.get("hhea_ascent") is not None:
            font["hhea"].ascent = int(round(identity["hhea_ascent"] * scale))
        if identity.get("hhea_descent") is not None:
            font["hhea"].descent = int(round(identity["hhea_descent"] * scale))
        if identity.get("hhea_lineGap") is not None:
            font["hhea"].lineGap = int(round(identity["hhea_lineGap"] * scale))


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
        font.recalcBBoxes = False
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


_LATIN_CODEPOINT_MAX = 0x2E80
_EXCLUDED_CODEPOINTS = frozenset({
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007,
    0x2008, 0x2009, 0x200A, 0x200B, 0x202F, 0x205F, 0x3000, 0xFEFF
})


def transplant_latin_glyphs(src_font, target_face) -> int:
    """Transplants non-CJK (Latin/Greek/Cyrillic/Math/Symbols) glyphs from src_font into target_face.
    
    Overwrites glyph outlines in place by codepoint using target_face's cmap, preserving
    exact glyph count, GIDs, and all CJK ideographs (>= 0x2E80).
    """
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    src_upm = getattr(src_font["head"], "unitsPerEm", 2048) or 2048
    tgt_upm = getattr(target_face["head"], "unitsPerEm", 2048) or 2048
    scale = float(tgt_upm) / float(src_upm)

    src_cmap = src_font.getBestCmap() or {}
    tgt_cmap = target_face.getBestCmap() or {}

    if "glyf" not in src_font or "glyf" not in target_face:
        return 0

    src_glyf = src_font["glyf"]
    tgt_glyf = target_face["glyf"]
    src_hmtx = src_font["hmtx"]
    tgt_hmtx = target_face["hmtx"]
    src_glyph_set = src_font.getGlyphSet()

    # CJK Alias Guard: Protect glyphs that are also mapped to CJK codepoints
    cjk_glyphs = {gname for cp, gname in tgt_cmap.items() if cp >= _LATIN_CODEPOINT_MAX}

    head = target_face.get("head")
    maxp = target_face.get("maxp")
    hhea = target_face.get("hhea")

    max_yMax = getattr(target_face["OS/2"], "usWinAscent", 2048) if "OS/2" in target_face else 2048
    min_yMin = -getattr(target_face["OS/2"], "usWinDescent", 512) if "OS/2" in target_face else -512

    transplanted_count = 0
    modified_names = set()
    for code, src_gname in src_cmap.items():
        if code >= _LATIN_CODEPOINT_MAX or code in _EXCLUDED_CODEPOINTS:
            continue

        # Protect Korean Hangul Jamo (0x1100-0x11FF) & Enclosed CJK Alphanumerics (0x2460-0x24FF)
        if 0x1100 <= code <= 0x11FF or 0x2460 <= code <= 0x24FF:
            continue

        ch = chr(code)
        # East Asian Ambiguous Punctuation Guard:
        # Protects fullwidth em dashes (——), ellipsis (……), curly quotes (“”), middle dot (·).
        # Allows European letters (é, ß, Æ, Ø) and digits (0-9) to transplant freely.
        eaw = unicodedata.east_asian_width(ch)
        if eaw == "A" and not unicodedata.category(ch).startswith(("L", "N")):
            continue

        tgt_gname = tgt_cmap.get(code)
        if not tgt_gname or tgt_gname not in tgt_glyf or tgt_gname in cjk_glyphs:
            continue

        try:
            rec_pen = DecomposingRecordingPen(src_glyph_set, skipMissingComponents=True, reverseFlipped=True)
            src_glyph_set[src_gname].draw(rec_pen)
            tgt_pen = TTGlyphPen(glyphSet=None)
            trans_pen = TransformPen(tgt_pen, (scale, 0, 0, scale, 0, 0))
            rec_pen.replay(trans_pen)
            new_glyph = tgt_pen.glyph()
            new_glyph.removeHinting()
            new_glyph.recalcBounds(None)
            tgt_glyf[tgt_gname] = new_glyph

            src_w, _ = src_hmtx[src_gname]
            scaled_advance = int(round(src_w * scale))
            new_lsb = getattr(new_glyph, "xMin", 0)
            tgt_hmtx[tgt_gname] = (scaled_advance, new_lsb)

            if hasattr(new_glyph, "yMax") and new_glyph.yMax > max_yMax:
                max_yMax = new_glyph.yMax
            if hasattr(new_glyph, "yMin") and new_glyph.yMin < min_yMin:
                min_yMin = new_glyph.yMin

            # Insurance: update head, maxp, and hhea limits if transplanted glyph exceeds donor boundaries
            if head is not None:
                if hasattr(new_glyph, "xMin") and new_glyph.xMin < head.xMin:
                    head.xMin = new_glyph.xMin
                if hasattr(new_glyph, "yMin") and new_glyph.yMin < head.yMin:
                    head.yMin = new_glyph.yMin
                if hasattr(new_glyph, "xMax") and new_glyph.xMax > head.xMax:
                    head.xMax = new_glyph.xMax
                if hasattr(new_glyph, "yMax") and new_glyph.yMax > head.yMax:
                    head.yMax = new_glyph.yMax

            if maxp is not None and getattr(new_glyph, "numberOfContours", 0) > 0:
                nPoints = len(new_glyph.coordinates)
                nContours = len(new_glyph.endPtsOfContours)
                if nPoints > maxp.maxPoints:
                    maxp.maxPoints = nPoints
                if nContours > maxp.maxContours:
                    maxp.maxContours = nContours

            if hhea is not None and scaled_advance > hhea.advanceWidthMax:
                hhea.advanceWidthMax = scaled_advance

            transplanted_count += 1
            modified_names.add(tgt_gname)
        except Exception:
            continue

    # Fix ONLY composites that (transitively) reference a transplanted glyph.
    # Every other glyph stays raw bytes -> fontTools writes it through untouched.
    if hasattr(tgt_glyf, "glyphs"):
        comps = {}
        for gname, raw in tgt_glyf.glyphs.items():
            if hasattr(raw, "data"):                      # still raw: peek contour count
                if raw.data and len(raw.data) >= 2 and struct.unpack(">h", raw.data[:2])[0] < 0:
                    comps[gname] = [c.glyphName for c in tgt_glyf[gname].components]
            elif getattr(raw, "numberOfContours", 0) < 0:  # already expanded composite
                comps[gname] = [c.glyphName for c in raw.components]

        affected = set(modified_names)
        changed = True
        while changed:                                    # propagate through nested composites
            changed = False
            for gname, kids in comps.items():
                if gname not in affected and any(k in affected for k in kids):
                    affected.add(gname)
                    changed = True

        for _ in range(2):                                # two passes for nested composite bounds propagation
            for gname in affected:
                g = tgt_glyf[gname]
                if getattr(g, "numberOfContours", 0) < 0 and hasattr(g, "recalcBounds"):
                    g.recalcBounds(tgt_glyf)
                    if gname in tgt_hmtx.metrics and hasattr(g, "xMin"):
                        adv, _ = tgt_hmtx.metrics[gname]
                        tgt_hmtx.metrics[gname] = (adv, g.xMin)

    # Explicitly synchronize No-Break Space (0x00A0) advance width with normal Space (0x0020)
    sp_gname = tgt_cmap.get(0x0020)
    nbsp_gname = tgt_cmap.get(0x00A0)
    if sp_gname and nbsp_gname and sp_gname in tgt_hmtx.metrics and nbsp_gname in tgt_hmtx.metrics:
        tgt_hmtx[nbsp_gname] = (tgt_hmtx[sp_gname][0], tgt_hmtx[nbsp_gname][1])

    # Strip obsolete pre-computed GDI width and height cheat-sheets (hdmx, LTSH, VDMX)
    # Keep valid position deltas: kern and GPOS remain intact!
    for tag in ("hdmx", "LTSH", "VDMX"):
        if tag in target_face:
            del target_face[tag]

    # Harmonize all three metric sets (sTypo, hhea, usWin) so GDI and DirectWrite agree 100% on line heights:
    ascent = max(int(max_yMax), getattr(target_face["OS/2"], "usWinAscent", 2048) if "OS/2" in target_face else 2048)
    descent = max(abs(int(min_yMin)), getattr(target_face["OS/2"], "usWinDescent", 512) if "OS/2" in target_face else 512)

    if "OS/2" in target_face:
        target_face["OS/2"].sTypoAscender = ascent
        target_face["OS/2"].sTypoDescender = -descent
        target_face["OS/2"].sTypoLineGap = 0
        target_face["OS/2"].usWinAscent = ascent
        target_face["OS/2"].usWinDescent = descent

    if "hhea" in target_face:
        target_face["hhea"].ascent = ascent
        target_face["hhea"].descent = -descent
        target_face["hhea"].lineGap = 0

    return transplanted_count


def build_hybrid_regional_font(source_path, donor_path, output_path):
    """Builds a hybrid regional font by transplanting Latin glyphs from source_path
    into the authentic donor font (TTC collection or TTF font).
    source_path can be a single Path or a list of Paths matching TTC face indices.
    """
    from fontTools.ttLib import TTCollection

    if isinstance(source_path, (list, tuple)):
        src_paths = [Path(p) for p in source_path]
    else:
        src_paths = [Path(source_path)]

    donor_path = Path(donor_path)
    output_path = Path(output_path)

    for p in src_paths:
        if not p.exists():
            raise FileNotFoundError(f"Source font not found: {p}")
    if not donor_path.exists():
        raise FileNotFoundError(f"Donor font not found: {donor_path}")

    if donor_path.suffix.lower() == ".ttc":
        coll = TTCollection(str(donor_path))
        try:
            for idx, face in enumerate(coll.fonts):
                face.recalcBBoxes = False
                src_p = src_paths[min(idx, len(src_paths) - 1)]
                src_font = TTFont(str(src_p))
                try:
                    transplant_latin_glyphs(src_font, face)
                finally:
                    src_font.close()
                if "DSIG" in face:
                    del face["DSIG"]
            coll.save(str(output_path))
        finally:
            coll.close()
    else:
        src_font = TTFont(str(src_paths[0]))
        try:
            donor_font = TTFont(str(donor_path))
            try:
                donor_font.recalcBBoxes = False
                transplant_latin_glyphs(src_font, donor_font)
                if "DSIG" in donor_font:
                    del donor_font["DSIG"]
                donor_font.save(str(output_path))
            finally:
                donor_font.close()
        finally:
            src_font.close()

    return str(output_path)

