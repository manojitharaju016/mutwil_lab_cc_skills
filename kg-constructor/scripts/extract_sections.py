"""
Deterministic section extraction for plant-paper JSONs.

Ported from anthropic_batch.py (plant_kg_construction) without any dependency on
the anthropic SDK or the Batch API. This module is pure stdlib.

Public surface:
    extract_sections(data) -> dict[str, str]
        sections.keys() includes:
            'abstract', 'introduction', 'results', 'discussion',
            'results_and_discussion', 'dive',
            optionally 'custom_<safe>' / 'results_and_discussion_<safe>' for
            review-paper / non-standard sections, plus '_header_<key>' entries
            preserving the original header text for custom sections.
    normalize_section_key(name) -> str
    BOILERPLATE_SECTIONS, FORWARD_LOOKING_KEYWORDS, MONTH_NAMES
"""

import re
from collections import defaultdict


MONTH_ORDER = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
MONTH_NAMES = {v: k.capitalize() for k, v in MONTH_ORDER.items()}


BOILERPLATE_SECTIONS = {
    "acknowledgements", "acknowledgments", "acknowledgement",
    "conflicts of interest", "conflict of interest", "conflict of interests",
    "conflict of interest statement", "competing interests",
    "competing financial interests", "declaration of interest",
    "declaration of interests", "declaration of competing interest",
    "author contributions", "author contribution", "authors' contributions",
    "authors' contribution", "authors contributions", "contributions",
    "graphical abstract",
    "supporting information", "supplementary material", "supplementary data",
    "data availability statement", "data availability", "data and code availability",
    "code availability", "open research", "related",
    "funding", "funding information", "disclaimer",
    "accession numbers", "accession number",
    "reference", "references", "references and recommended reading",
    "summary statement", "ethics approval",
    "conflicts of interests", "uncited references",
    "credit authorship contribution statement",
    "data statement", "data access statement",
    "source data", "electronic supplementary material",
    "relevant articles", "availability of materials",
    "methods", "methods summary", "online methods",
    "materials and methods", "material and methods",
    "experimental procedures", "experimental methods",
    "methodology", "methodologies", "methodological considerations",
    "experimental design", "experimental section",
    "materials and method",
    "methods and materials", "test materials and methods",
    "experimental materials as well as methods",
    "additional methods", "other methods",
    "quantification and statistical analysis",
    "star methods", "resource availability",
    "comments",
    "get full access to this article",
    "abbreviations", "abbreviations:", "abbreviation", "abbreviation:",
    "accession codes", "accession code",
    "powerpoint slides", "extended data figures and tables",
    "extended data", "extended data tables",
    "integrated supplementary information",
    "key resources table", "lead contact",
    "contact for reagent and resource sharing",
    "plant material", "plant materials",
    "plant material and growth conditions",
    "plant materials and growth conditions",
    "materials and growth conditions",
    "plant growth and rna assays",
    "genetic stocks and growth conditions",
    "biological materials",
    "arabidopsis materials and growth conditions",
    "plant materials, human cells, and growth conditions",
    "plant material and reverse genetics",
    "plant materials and genetic analysis",
    "plant strains", "mutant plant strains",
    "supplemental data", "supplemental information",
    "note added in proof",
    "statistical analysis", "statistical analysis of results",
    "consortia",
    "additional data files", "additional files", "additional file",
    "description of additional files",
    "additional data", "additional material",
    "author details", "authors' information", "authors' details",
    "competing interest", "declaration of competing interests",
    "pre-publication history",
    "disclosure statement",
    "figures", "figure legends", "figure legend",
    "authors' original submitted files for images",
    "preface", "compilation", "in retrospect", "looking back",
    "looking ahead", "epilogue", "prologue",
    "early years", "the early years", "early years and education",
    "early days of my education", "early years in postwar germany",
    "childhood", "teaching", "opinions on opportunities and the gender gap",
    "retirement and beyond", "looking back at life",
    "footnotes",
    "future perspectives", "future perspective",
    "future directions", "future direction",
    "future research", "future work", "future studies",
    "outlook", "future outlook",
    "concluding perspectives",
    "open questions", "unanswered questions", "open issues",
}


FORWARD_LOOKING_KEYWORDS = {
    "future", "outlook", "prospects", "prospect",
    "concluding remarks", "concluding comments", "concluding perspectives",
    "perspectives", "perspective",
    "moving forward", "where to go from here",
    "open questions", "unanswered questions", "open issues",
    "what lies in the future", "emerging questions",
    "back to the basics",
    "research priorities", "research priority",
    "research needs", "research recommendations", "research roadmap",
    "research agenda", "research questions", "research challenges",
    "research gaps", "knowledge gaps",
}


_ARABIC_PREFIX_RE = re.compile(r'^\d+[\.\s]+')


def _is_forward_looking_section(norm_name):
    for kw in FORWARD_LOOKING_KEYWORDS:
        if kw in norm_name:
            return True
    return False


def clean_section_text(text):
    if not text:
        return ""
    header_pattern = re.compile(r'#\$.*?#\$')
    return header_pattern.sub('', text).strip()


def clean_dive_terms(text):
    text = clean_section_text(text)
    lines = text.split('\n')
    seen = set()
    deduped = []
    for line in lines:
        s_line = line.strip()
        if not s_line:
            continue
        if s_line not in seen:
            seen.add(s_line)
            deduped.append(line)
    return "\n".join(deduped).strip()


def normalize_section_name(name):
    if not name:
        return ""
    norm = name.lower().replace("&", "and").replace("/", " ")
    for ch in "★✪✸✣☆●◆▼▶◀":
        norm = norm.replace(ch, " ")
    norm = re.sub(r'\s+', ' ', norm).strip()
    return norm


def section_matches(section_name, keywords):
    norm = normalize_section_name(section_name)
    for kw in keywords:
        if kw == "main":
            if re.search(r'\bmain\b', norm):
                return True
        elif kw in norm:
            return True
    return False


def normalize_section_key(name):
    if not name:
        return ""
    norm = name.lower().replace("&", "and").replace("/", " ")
    for ch in "★✪✸✣☆●◆▼▶◀":
        norm = norm.replace(ch, " ")
    norm = re.sub(r'\s+', ' ', norm).strip()
    norm = _ARABIC_PREFIX_RE.sub('', norm).strip()
    return norm


STAR_METHODS_MARKERS = {
    'experimental procedures', 'star methods', 'experimental section',
    'key resources table', 'lead contact',
    'contact for reagent and resource sharing',
    'plant material', 'plant materials',
    'plant material and growth conditions',
    'plant materials and growth conditions',
    'materials and growth conditions',
    'genetic stocks and growth conditions',
    'biological materials',
    'arabidopsis materials and growth conditions',
    'plant materials, human cells, and growth conditions',
    'plant material and reverse genetics',
    'plant materials and genetic analysis',
    'plant strains', 'mutant plant strains',
}


POST_DISCUSSION_METHODS = {
    'plants', 'bacteria', 'transgenic plants', 'transgenic lines',
    'protein', 'rna', 'antibodies', 'constructs', 'microscopy',
    'plant growth', 'mutant isolation', 'plant strains',
    'mutant plant strains', 'loss-of-function mutants',
    'genetic analysis', 'data release', 'data handling',
}


# Canonical body-section names that must NEVER be reclassified as methods by
# the `_content_methods_sections` pre-scan, even when they appear after a
# `## Materials and methods` marker in the `content` field. (Necessary for
# OUP/Wiley papers whose content field orders Methods -> Results -> Discussion;
# without this guard the pre-scan would silently drop Results+Discussion.)
CANONICAL_BODY_SECTIONS = {
    "abstract", "summary",
    "introduction", "background", "main",
    "results", "result", "findings", "finding",
    "discussion", "conclusion", "conclusions", "concluding remarks",
    "results and discussion",
}


_AUTOBIO_RE = re.compile(
    r'\buniversity\b|\bcollege\b|\binstitute\b'
    r'|\bph\.?d\.?\b|\bpostdoc|\bgraduate\b|\bundergraduate'
    r'|\bsabbatical|\bretirement|\bemeritus'
    r'|\bmy teenage|\bmy life|\bmy career'
    r'|\bbitten by the research|\bimmersion into'
    r'|\bmotivation to enter|\brecreational basis'
    r'|\bplant biologist by default'
    r'|\bcaltech\b|\bstanford\b|\bharvard\b|\bmit\b|\bberkeley\b'
    r'|\bcornell\b|\bmichigan\b|\bwageningen\b|\bmcmaster\b'
    r'|\bcologne\b|\bmax planck\b|\byale\b|\bduke\b'
    r'|\bpeking\b|\bshanghai\b|\bwuxi\b|\briken\b|\bbasel\b'
    r'|\bgöttingen\b|\btübingen\b|\bmaryland\b'
    r'|\bworld war|\bmilitary service'
    r'|\bafter university\b|\bfinal years in'
    r'|\blooking back|\blooking ahead|\bin retrospect'
    r'|\bpreface\b|\bteaching\b|\bearly education'
    r'|\bearly years|\bchildhood',
    re.IGNORECASE,
)


_METHODS_KEYWORDS_RE = re.compile(
    r'microscop|staining|\bassays?\b|cloning\b|plasmid|primers?\b|^plant material'
    r'|purification|immunoblot|transformation\b|hybridization'
    r'|\bpcr\b|sequencing\b|western blot|northern blot|southern blot'
    r'|immunofluorescence|immunolocalization|immunoprecipitation'
    r'|electrophor|crystalliz|recombinant protein|protein expression'
    r'|binding assay|activity assay|kinase assay|\bchip\b'
    r'|gel filtration|bisulfite|rna extract|rna analys|\bblots?\b'
    r'|rt[- ]?pcr|real[- ]?time.+pcr|quantitative.+pcr'
    r'|transient expression|particle bombardment|gene expression profil'
    r'|growth measurement|phenotypic analysis|mutant isolation'
    r'|plant transformation|agrobacterium|map.based cloning'
    r'|\bantibod|\bconstruct[s]?\b|yeast two.hybrid|bifc',
    re.IGNORECASE,
)


def extract_sections(data):
    sections = {}

    items = []
    dive_terms_text = ""
    if isinstance(data, dict):
        items = data.get("full_text", [])
        if not items:
            items = data.get("sections", [])
        if not items and "structure" in data:
            items = data["structure"]
        dive_terms_text = data.get("dive_curated_terms", "")
    elif isinstance(data, list):
        items = data

    sec_map = defaultdict(list)

    if isinstance(data, dict) and data.get("abstract"):
        abs_text = clean_section_text(data["abstract"])
        if abs_text:
            sec_map['abstract'].append(abs_text)

    DIVE_SECTION_NAMES = {"dive curated terms", "glossary"}

    dive_terms = []
    if dive_terms_text:
        dive_terms.append(clean_dive_terms(dive_terms_text))

    if not dive_terms_text:
        for item in items:
            header = item.get("section_header") or item.get("section_name", "")
            if header and header.strip().lower() in DIVE_SECTION_NAMES:
                if "sub_sections" in item and isinstance(item["sub_sections"], dict):
                    parts = [str(v) for v in item["sub_sections"].values()]
                    dive_section_text = "\n".join(parts)
                elif "section_text" in item and isinstance(item["section_text"], str):
                    dive_section_text = item["section_text"]
                else:
                    dive_section_text = ""
                if dive_section_text.strip():
                    dive_terms.append(clean_dive_terms(dive_section_text))
                break
    sections['dive'] = "\n".join(dive_terms)

    custom_sections = []

    star_methods_reached = False
    discussion_seen = False
    in_results_and_discussion = False

    _content_methods_sections = set()
    _content_rnd_sections = set()
    if isinstance(data, dict):
        _ct = (data.get("content") or "").strip()
        if _ct:
            _rnd_marker = re.search(
                r'^##\s+Results and Discussion\s*$',
                _ct, re.MULTILINE | re.IGNORECASE,
            )
            if _rnd_marker:
                _rnd_end = re.search(
                    r'^##\s+(Discussion|Conclusion|Experimental Procedures|STAR Methods|Materials and Methods)\s*$',
                    _ct[_rnd_marker.end():], re.MULTILINE | re.IGNORECASE,
                )
                _rnd_block = _ct[_rnd_marker.end():_rnd_marker.end() + _rnd_end.start()] if _rnd_end else _ct[_rnd_marker.end():]
                for _hm in re.finditer(r'^##\s+(.+)', _rnd_block, re.MULTILINE):
                    _content_rnd_sections.add(normalize_section_key(_hm.group(1).strip()))

            _methods_marker = re.search(
                r'^##\s+(Experimental Procedures|STAR Methods|Materials and Methods|Experimental Section)\s*$',
                _ct, re.MULTILINE | re.IGNORECASE,
            )
            if _methods_marker:
                _before_marker = set()
                for _hm in re.finditer(r'^##\s+(.+)', _ct[:_methods_marker.start()], re.MULTILINE):
                    _before_marker.add(normalize_section_key(_hm.group(1).strip()))
                for _hm in re.finditer(r'^##\s+(.+)', _ct[_methods_marker.end():], re.MULTILINE):
                    _hdr_norm = normalize_section_key(_hm.group(1).strip())
                    if (_hdr_norm not in BOILERPLATE_SECTIONS
                            and not _is_forward_looking_section(_hdr_norm)
                            and _hdr_norm not in _before_marker
                            and _hdr_norm not in CANONICAL_BODY_SECTIONS):
                        _content_methods_sections.add(_hdr_norm)

    for item in items:
        header = item.get("section_header") or item.get("section_name", "")
        if not header:
            continue

        content = ""
        if "section_text" in item and isinstance(item["section_text"], str) and item["section_text"].strip():
            content = item["section_text"]
        elif "sub_sections" in item and isinstance(item["sub_sections"], dict):
            parts = [str(v) for v in item["sub_sections"].values()]
            content = "\n".join(parts)
        elif "section_text" in item and isinstance(item["section_text"], list):
            content = "\n".join(item["section_text"])

        clean_content = clean_section_text(content)
        if not clean_content:
            continue

        norm = normalize_section_key(header)

        if norm in BOILERPLATE_SECTIONS or _is_forward_looking_section(norm):
            if norm in STAR_METHODS_MARKERS:
                star_methods_reached = True
            continue

        if star_methods_reached:
            continue

        if norm in _content_methods_sections:
            star_methods_reached = True
            continue

        if _METHODS_KEYWORDS_RE.search(norm):
            if discussion_seen:
                star_methods_reached = True
                continue
            if len(norm) < 90 and not any(kw in norm for kw in
                    ['role', 'mechanism', 'model', 'effect', 'function',
                     'regulation', 'pathway', 'signal', 'response', 'identif',
                     'required', 'mediate', 'control', 'involve', 'reveal']):
                star_methods_reached = True
                continue
        if discussion_seen and norm in POST_DISCUSSION_METHODS:
            star_methods_reached = True
            continue

        if section_matches(header, ["abstract", "summary"]):
            sec_map['abstract'].append(clean_content)
        elif section_matches(header, ["introduction", "background", "main"]):
            sec_map['introduction'].append(clean_content)
        elif section_matches(header, ["results and discussion"]):
            sec_map['results_and_discussion'].append(clean_content)
            in_results_and_discussion = True
        elif section_matches(header, ["result", "finding"]):
            sec_map['results'].append(clean_content)
        elif section_matches(header, ["discussion", "conclusion"]):
            sec_map['discussion'].append(clean_content)
            discussion_seen = True
            in_results_and_discussion = False
        elif header.strip().lower() in DIVE_SECTION_NAMES:
            continue
        else:
            content_lower = clean_content[:300].lower()
            ack_markers = ["we thank", "we acknowledge", "this work was supported",
                           "this research was funded", "the authors declare",
                           "no conflict", "funding information",
                           "the authors would like to thank"]
            if len(clean_content) < 500 and any(m in content_lower for m in ack_markers):
                continue

            if _AUTOBIO_RE.search(norm):
                continue

            if not in_results_and_discussion and norm in _content_rnd_sections:
                in_results_and_discussion = True
            prefix = "results_and_discussion" if in_results_and_discussion else "custom"
            safe_key = re.sub(r'[^a-z0-9]+', '_', norm).strip('_')[:50]
            if not safe_key:
                safe_key = prefix
            base_key = f"{prefix}_{safe_key}"
            key = base_key
            counter = 2
            while key in sections:
                key = f"{base_key}_{counter}"
                counter += 1
            custom_sections.append((key, header.strip(), clean_content))

    has_standard_sections = any(sec_map[k] for k in ['introduction', 'results', 'discussion'])
    missing_key_sections = (
        not sec_map['results'] and not sec_map.get('results_and_discussion')
    ) or not sec_map['discussion']
    sections_need_content_fallback = not has_standard_sections or missing_key_sections

    if isinstance(data, dict):
        content_text = (data.get("content") or "").strip()
        if content_text:
            header_splits = re.split(r'\n(?=##\s+)', content_text)

            if len(header_splits) > 1 and sections_need_content_fallback:
                def _section_needs_fill(key):
                    existing = "".join(sec_map.get(key, []))
                    if not existing.strip():
                        return True
                    stripped = re.sub(r'#[$].*?#[$]', '', existing, flags=re.DOTALL).strip()
                    return len(stripped) < 200

                content_star_methods_reached = False
                content_discussion_seen = False
                content_in_rnd = False
                for chunk in header_splits:
                    header_match = re.match(r'^##\s+(.+)\n', chunk)
                    if header_match:
                        header = header_match.group(1).strip()
                        body = chunk[header_match.end():].strip()
                        body = clean_section_text(body)
                        norm = normalize_section_key(header)
                        if not body:
                            if norm in BOILERPLATE_SECTIONS and norm in STAR_METHODS_MARKERS:
                                content_star_methods_reached = True
                            elif norm in _content_methods_sections:
                                content_star_methods_reached = True
                            elif section_matches(header, ["discussion", "conclusion"]):
                                content_discussion_seen = True
                                content_in_rnd = False
                            elif section_matches(header, ["results and discussion"]):
                                content_in_rnd = True
                            continue
                        if norm in BOILERPLATE_SECTIONS or _is_forward_looking_section(norm):
                            if norm in STAR_METHODS_MARKERS:
                                content_star_methods_reached = True
                            continue
                        if content_star_methods_reached:
                            continue
                        if norm in _content_methods_sections:
                            content_star_methods_reached = True
                            continue
                        if content_discussion_seen and (norm in POST_DISCUSSION_METHODS or _METHODS_KEYWORDS_RE.search(norm)):
                            content_star_methods_reached = True
                            continue
                        elif section_matches(header, ["abstract", "summary"]):
                            if _section_needs_fill('abstract'):
                                sec_map['abstract'] = [body]
                        elif section_matches(header, ["introduction", "background", "main"]):
                            if _section_needs_fill('introduction'):
                                sec_map['introduction'] = [body]
                        elif section_matches(header, ["results and discussion"]):
                            if _section_needs_fill('results_and_discussion'):
                                sec_map['results_and_discussion'] = [body]
                            content_in_rnd = True
                        elif section_matches(header, ["result", "finding"]):
                            if _section_needs_fill('results'):
                                sec_map['results'] = [body]
                        elif section_matches(header, ["discussion", "conclusion"]):
                            if _section_needs_fill('discussion'):
                                sec_map['discussion'] = [body]
                            content_discussion_seen = True
                            content_in_rnd = False
                        else:
                            if _AUTOBIO_RE.search(norm):
                                continue
                            _already = any(norm == normalize_section_key(h) for _, h, _ in custom_sections)
                            if _already:
                                continue
                            _prefix = "results_and_discussion" if content_in_rnd else "custom"
                            safe_key = re.sub(r'[^a-z0-9]+', '_', norm).strip('_')[:50]
                            if not safe_key:
                                safe_key = _prefix
                            base_key = f"{_prefix}_{safe_key}"
                            key = base_key
                            counter = 2
                            while key in sections:
                                key = f"{base_key}_{counter}"
                                counter += 1
                            custom_sections.append((key, header, body))
                    else:
                        preamble = clean_section_text(chunk)
                        if preamble and len(preamble) > 50 and not sec_map['abstract']:
                            sec_map['abstract'].append(preamble)

            elif sections_need_content_fallback:
                if not sec_map['abstract']:
                    abstract_match = re.search(
                        r'(?:^|\n)###?\s*(?:abstract|summary)\s*\n(.*?)(?=\n##|\Z)',
                        content_text, re.IGNORECASE | re.DOTALL,
                    )
                    if abstract_match:
                        abs_text = clean_section_text(abstract_match.group(1).strip())
                        if abs_text:
                            sec_map['abstract'].append(abs_text)

                has_any_body = (
                    any(sec_map[k] for k in ['introduction', 'results', 'discussion', 'results_and_discussion'])
                    or custom_sections
                )
                has_any_extracted = any(sec_map[k] for k in ['abstract']) or has_any_body
                if not has_any_extracted:
                    cleaned = clean_section_text(content_text)
                    if len(cleaned) > 50:
                        custom_sections.append(("custom_full_body", "Full Text Body", cleaned))
                elif not has_any_body:
                    cleaned = clean_section_text(content_text)
                    existing_abstract = "\n\n".join(sec_map.get('abstract', []))
                    if len(cleaned) > 50 and cleaned != existing_abstract:
                        custom_sections.append(("custom_full_body", "Full Text Body", cleaned))

    for k in ['abstract', 'introduction', 'results', 'discussion']:
        sections[k] = "\n\n".join(sec_map[k])

    sections['results_and_discussion'] = "\n\n".join(sec_map.get('results_and_discussion', []))

    for key, header_text, content in custom_sections:
        sections[key] = content
        sections[f"_header_{key}"] = header_text

    return sections


def extract_abbreviations(data):
    """Return abbreviation block text from a paper JSON, or empty string."""
    if not isinstance(data, dict):
        return ""
    for sec in (data.get("sections") or data.get("full_text") or []):
        sn = (sec.get("section_name") or sec.get("section_header") or "").strip().lower()
        if "abbreviat" in sn:
            if isinstance(sec.get("section_text"), str):
                return sec["section_text"].strip()
            if isinstance(sec.get("sub_sections"), dict):
                return "\n".join(str(v) for v in sec["sub_sections"].values()).strip()
            if isinstance(sec.get("section_text"), list):
                return "\n".join(sec["section_text"]).strip()
            break
    return ""
