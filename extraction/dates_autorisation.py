"""Colonnes « Date de début / fin d'autorisation ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         LES DEUX DATES
# ====================================================================
def _to_str(x):
    if x is None: return ""
    if isinstance(x, list): return "\n".join(str(s) for s in x if s)
    return str(x)


def _numbered(s: str, prefix: str) -> str:
    lines = (s or "").splitlines()
    return "\n".join(f"{prefix}{i+1:04d}: {l}" for i, l in enumerate(lines))


def _pick_last_valid_result_block(decoded: str) -> str:
    lower = decoded.lower()
    if "<r>" in lower and "</r>" in lower:
        parts = decoded.split("<r>")
        for part in reversed(parts[1:]):
            body = part.split("</r>")[0].strip()
            if "jj/mm/aaaa" in body.lower() or "<n ans" in body.lower():
                continue
            return body
    return decoded.strip()


def _run_llm(client, deployment, system_msg: str, user_msg: str, max_new_tokens: int = 4000, debug: bool = False) -> str:
    try:
        response = traced_completion(client.chat.completions.create, 
            model=deployment,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_completion_tokens=max_new_tokens,
        )
        decoded = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[_run_llm] Azure OpenAI error: {e}")
        decoded = "non trouvee"
    if debug:
        print("DEBUG LLM RAW >>>", decoded[:2000], "<<< END")
    return _pick_last_valid_result_block(decoded)


MONTH_RE = r"(janvier|f[eE]vrier|fevrier|mars|avril|mai|juin|juillet|ao[uU]t|aout|septembre|octobre|novembre|d[eE]cembre|decembre)"

MOIS_NUM = {
    "janvier": 1, "fevrier": 2, "mars": 3,
    "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "decembre": 12,
}

RE_SLASH = re.compile(r"\b([0-3]?\d)\s*/\s*([01]?\d)\s*/\s*(\d{4})\b", re.I)
RE_DAY_MONTH_YEAR = re.compile(
    r"\b([0-3]?\d)(?:\s*er)?\s+" + MONTH_RE + r"\s+(\d{4})\b", re.I
)
RE_MONTH_YEAR = re.compile(r"\b" + MONTH_RE + r"\s+(\d{4})\b", re.I)


def _norm_for_match(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[.,:;\xb7\u2014\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _looks_like_date(val: str) -> bool:
    if not val or val.lower().startswith("non trouv"):
        return False
    s = _strip_accents(val)
    return bool(RE_SLASH.search(s) or RE_DAY_MONTH_YEAR.search(s) or RE_MONTH_YEAR.search(s))


def _hard_date_filter(val: str) -> str:
    if not val or val.lower().startswith("non trouv"):
        return "non trouvee"
    low = _strip_accents(val).lower()
    if any(k in low for k in (" ans", " mois", "jours", "renouvel", "a compter")):
        return "non trouvee"
    return val if _looks_like_date(val) else "non trouvee"


def _is_verbatim_in(src: str, candidate: str) -> bool:
    if not candidate or candidate.lower().startswith("non trouv"):
        return False

    src_norm = _norm_for_match(src or "")
    cand_norm = _norm_for_match(candidate)

    if cand_norm in src_norm:
        return True

    m = re.match(
        r'^([0-3]?\d)(?:\s*er)?\s+'
        r'(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)'
        r'\s+(\d{4})$',
        cand_norm,
        re.IGNORECASE
    )
    if m:
        day = m.group(1)
        month = m.group(2)
        year = m.group(3)

        if len(day) == 2:
            split_day = f"{day[0]} {day[1]}"
            alt = f"{split_day} {month} {year}"
            if alt in src_norm:
                return True

        min_len = max(3, len(month) - 2)
        max_len = len(month) + 2

        day_pattern = re.escape(day)
        if len(day) == 2:
            day_pattern = rf"(?:{re.escape(day)}|{re.escape(day[0])}\s+{re.escape(day[1])})"

        flex_pattern = (
            rf"\b{day_pattern}(?:\s*er)?\s+"
            rf"[a-z]{{{min_len},{max_len}}}\s+"
            rf"{re.escape(year)}\b"
        )
        if re.search(flex_pattern, src_norm, re.IGNORECASE):
            return True

    m = re.match(r'^([0-3]?\d)\s*/\s*([01]?\d)\s*/\s*(\d{4})$', cand_norm, re.IGNORECASE)
    if m:
        day = m.group(1)
        month = m.group(2)
        year = m.group(3)

        if len(day) == 2:
            split_day = f"{day[0]} {day[1]}"
            alt1 = f"{split_day} / {month} / {year}"
            alt2 = f"{split_day}/{month}/{year}"
            if alt1 in src_norm or alt2 in src_norm:
                return True

    return False


def _dedup_month_word(s: str) -> str:
    if not s or s.lower().startswith("non trouv"):
        return s
    return re.sub(rf"\b({MONTH_RE})\b\s+\b\1\b", r"\1", s, flags=re.I)


def _fix_broken_dates(text: str) -> str:
    if not text:
        return text

    mois = r"(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)"

    pattern1 = rf'(\b\d{{1,2}})\s*\n\s*({mois}\s+\d{{4}}\b)'
    pattern2 = rf'(\b\d{{1,2}})\s*\n\s*({mois})\s*\n\s*(\d{{4}}\b)'

    text = re.sub(pattern2, lambda m: f"{m.group(1)} {m.group(2)} {m.group(3)}", text, flags=re.IGNORECASE)
    text = re.sub(pattern1, lambda m: f"{m.group(1)} {m.group(2)}", text, flags=re.IGNORECASE)

    pattern_split_day_inline = re.compile(rf'\b([0-3])\s+([0-9])\s+{mois}\s+(\d{{4}})\b', re.IGNORECASE)

    def _merge_split_day_inline(m):
        d = f"{m.group(1)}{m.group(2)}"
        try:
            di = int(d)
        except:
            return m.group(0)
        if 1 <= di <= 31:
            return f"{d} {m.group(3)} {m.group(4)}"
        return m.group(0)

    text = pattern_split_day_inline.sub(_merge_split_day_inline, text)

    pattern_split_day_multiline = re.compile(rf'\b([0-3])\s*\n\s*([0-9])\s+{mois}\s+(\d{{4}})\b', re.IGNORECASE)

    def _merge_split_day_multiline(m):
        d = f"{m.group(1)}{m.group(2)}"
        try:
            di = int(d)
        except:
            return m.group(0)
        if 1 <= di <= 31:
            return f"{d} {m.group(3)} {m.group(4)}"
        return m.group(0)

    text = pattern_split_day_multiline.sub(_merge_split_day_multiline, text)

    pattern_split_day_slash = re.compile(r'\b([0-3])\s+([0-9])\s*/\s*([01]?\d)\s*/\s*(\d{4})\b', re.IGNORECASE)

    def _merge_split_day_slash(m):
        d = f"{m.group(1)}{m.group(2)}"
        try:
            di = int(d)
        except:
            return m.group(0)
        if 1 <= di <= 31:
            return f"{d}/{m.group(3)}/{m.group(4)}"
        return m.group(0)

    text = pattern_split_day_slash.sub(_merge_split_day_slash, text)

    return text


def _fix_ocr_text(text: str) -> str:
    if not text:
        return text

    OCR_DIGIT_FIXES = {
        's': '5', 'S': '5',
        'l': '1', 'I': '1', '|': '1',
        'O': '0', 'o': '0',
        'B': '8', 'b': '6',
    }

    def _fix_year(m):
        year = m.group(0)
        if year.isdigit():
            return year
        corrected = ""
        for ch in year:
            corrected += OCR_DIGIT_FIXES.get(ch, ch)
        return corrected

    text = re.sub(r'\b(19|20)\d[0-9a-zA-Z|]\b', _fix_year, text)
    text = re.sub(r"\bjusqu\s+au\b", "jusqu'au", text, flags=re.IGNORECASE)

    return text


def _complete_year_if_missing(date_txt: str, src: str, lookahead: int = 240) -> str:
    if not date_txt or date_txt.lower().startswith("non trouv"):
        return date_txt

    mois_grp = MONTH_RE
    m = re.match(rf"^\s*([0-3]?\d)\s*(?:er)?\s+{mois_grp}\s*$", date_txt, flags=re.I)
    if not m:
        return date_txt

    jj, mois = m.group(1), m.group(2)

    pat = re.compile(
        rf"([^\d]|^){jj}\s*(?:er)?\s+{mois}\b"
        rf"(?:(?!\b\d{{4}}\b).){{0,{lookahead}}}"
        rf"\b(\d{{4}})\b",
        re.I | re.S | re.U
    )

    m2 = pat.search(src or "")
    if m2:
        an = m2.group(2)
        return f"{jj} {mois} {an}"

    return date_txt


def _search_broken_fin(txt: str):
    MOIS_FR = MONTH_RE
    FIN_ANCH = r"(?i)(?:se\s+termine|pour\s+se\s+terminer|jusqu(?:'|'|\s)?au|expire\s+le|expiration\s*le|echeance\s*le|date\s+de\s+fin)"
    pat = re.compile(
        rf"{FIN_ANCH}.*?(?:\ble\b\s*)?"
        rf"([0-3]?\d)\s*(?:er)?\s*(?:\r?\n|\r|\s)+"
        rf"({MOIS_FR})\s*(?:\r?\n|\r|\s)*(?:([12]\d{{3}}))?",
        re.I | re.S | re.U
    )
    m = pat.search(txt or "")
    if not m:
        return None
    j, mois, an = m.group(1), m.group(2), m.group(3)
    date_txt = f"{j} {mois}".strip()
    if an:
        date_txt = f"{date_txt} {an}"
    return re.sub(r"\s+", " ", date_txt).strip()


def _extract_end_date_multiline(src: str, lookahead_year: int = 200, debug: bool = False):
    if not src:
        return None

    MOIS = MONTH_RE
    FIN_ANCH = r"(?i)(?:se\s+termine|pour\s+se\s+terminer|jusqu(?:'|'|\s)?au|expire\s+le|expiration\s*le|echeance\s*le|date\s+de\s+fin)"

    pat_jm = re.compile(
        rf"{FIN_ANCH}.*?"
        rf"(?:\b(?:le|ie)\b\s*)?"
        rf"(\d{{1,2}})\s*(?:er)?"
        rf"(?:\s*\n\s*)+"
        rf"({MOIS})",
        flags=re.I | re.S
    )

    m = pat_jm.search(src)
    if m:
        j, mois = m.group(1), m.group(2)
        end_pos = m.end()
        tail = src[end_pos:end_pos + 50]
        an_match = re.search(r'\b(\d{4})\b', tail)
        an = an_match.group(1) if an_match else None
        if an:
            result = f"{j} {mois} {an}"
            return re.sub(r'\s+', ' ', result).strip()
        else:
            return re.sub(r'\s+', ' ', f"{j} {mois}").strip()

    return None


def _parse_date_to_comparable(date_str):
    if not date_str or date_str.lower().startswith("non trouv"):
        return None

    m = re.match(r'(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})', date_str)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.match(
        r'(\d{1,2})\s*(?:er)?\s+'
        r'(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)'
        r'\s+(\d{4})',
        date_str, re.IGNORECASE
    )
    if m:
        mois_low = _strip_accents(m.group(2).lower())
        return (int(m.group(3)), MOIS_NUM.get(mois_low, 0), int(m.group(1)))

    m = re.match(
        r'(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)'
        r'\s+(\d{4})',
        date_str, re.IGNORECASE
    )
    if m:
        mois_low = _strip_accents(m.group(1).lower())
        return (int(m.group(2)), MOIS_NUM.get(mois_low, 0), 1)

    return None


def _remove_legal_reference_noise(text: str) -> str:
    if not text:
        return text

    m_article = re.search(r'(?i)\barticle\s*\d', text)
    if m_article:
        preamble = text[:m_article.start()]
        body = text[m_article.start():]
    else:
        preamble = text
        body = ""

    preamble = re.sub(r'(?im)^[ \t\-\u2013\u2014\u2022\*]*vu\b.*(?:\n|$)', '\n', preamble)

    LEGAL_NOISE_PATTERNS = [
        r'(?is)\bprotocole\b.*?(?:[;.]|$)',
        r'(?is)\bavenant\b.*?(?:[;.]|$)',
        r'(?is)\bdelib[eé]ration\b.*?(?:[;.]|$)',
        r'(?is)\bjournal officiel\b.*?(?:[;.]|$)',
        r'(?is)\bpublication\b.*?(?:[;.]|$)',
        r'(?is)\bconvention\b.*?(?:[;.]|$)',
    ]
    for pat in LEGAL_NOISE_PATTERNS:
        preamble = re.sub(pat, ' ', preamble)

    preamble = re.sub(r'[ \t]+', ' ', preamble)
    preamble = re.sub(r'\n{3,}', '\n\n', preamble)

    return (preamble.strip() + "\n" + body).strip()


def _find_next_date_after_contextual(anchors, text, lookahead=220, mode="start", debug=False):
    if not text:
        return None

    MONTHS = r"(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)"
    DATE_SLASH = r"[0-3]?\d\s*/\s*[01]?\d\s*/\s*\d{2,4}"
    DATE_DMY = rf"[0-3]?\d(?:\s*er)?\s+{MONTHS}\s+\d{{4}}"
    DATE_MY = rf"{MONTHS}\s+\d{{4}}"

    RE_S = re.compile(DATE_SLASH, re.I | re.U)
    RE_D = re.compile(DATE_DMY, re.I | re.U)
    RE_M = re.compile(DATE_MY, re.I | re.U)

    POSITIVE_CTX = [
        r"\bautorisation\b",
        r"\bpresente\s+autorisation\b",
        r"\bpr[eé]sente\s+autorisation\b",
        r"\bpermission\b",
        r"\boccupation\b",
        r"\bduree\b",
        r"\bdur[eé]e\b",
        r"\bvalidit[eé]\b",
        r"\bvalable\b",
        r"\bexpire\b",
        r"\bexpiration\b",
        r"\becheance\b",
        r"\b[eé]ch[eé]ance\b",
    ]

    NEGATIVE_CTX = [
        r"\bprotocole\b",
        r"\bavenant\b",
        r"\bdeliberation\b",
        r"\bd[eé]lib[eé]ration\b",
        r"\bconseil\b",
        r"\bd[eé]cret\b",
        r"\bvu\s+(?:l['']\s*)?arr[eê]t[eé]\b",
        r"\bloi\b",
        r"\bconvention\b",
        r"\bjournal officiel\b",
        r"\bpublication\b",
        r"\bsign[eé]\b",
        r"\bsigne\b",
        r"\bvu\b",
    ]

    def _has_negative_context(ctx: str) -> bool:
        return any(re.search(p, ctx, re.I | re.U) for p in NEGATIVE_CTX)

    def _has_positive_context(ctx: str) -> bool:
        return any(re.search(p, ctx, re.I | re.U) for p in POSITIVE_CTX)

    for anc in anchors:
        for mm in re.finditer(anc, text, flags=re.IGNORECASE | re.UNICODE):
            left_ctx = text[max(0, mm.start() - 70): mm.start()]
            right_ctx = text[mm.end(): mm.end() + lookahead]
            local_ctx = left_ctx + " " + right_ctx

            if _has_negative_context(local_ctx):
                continue

            ms = RE_S.search(right_ctx) or RE_D.search(right_ctx) or RE_M.search(right_ctx)
            if not ms:
                continue

            candidate = ms.group(0).strip()

            if mode == "start":
                if not _has_positive_context(local_ctx):
                    continue

            return candidate

    return None


_CTX_CIRCULATION_RE = re.compile(
    r"\b(?:circulation|vehicules?|stationnement|restreinte?s?|deviation|alternat|chantiers?|travaux)\b")
_CTX_TRAVAUX_AVANT_RE = re.compile(
    r"\b(?:(?:debut|fin|date|ouverture|demarrage)\s+(?:des\s+|de\s+|du\s+)?(?:travaux|chantier|intervention)"
    r"|travaux\s+(?:debuteront|commenceront|se\s+derouleront|auront\s+lieu|seront\s+(?:realises|executes)"
    r"|pourront\s+(?:etre\s+)?(?:realises|executes|entrepris|debuter|commencer))"
    r"|(?:chantier|intervention)s?\b)")
_CTX_AUTORISATION_RE = re.compile(
    r"\b(?:autoris\w*|permission|occupation|permis|valable|accord\w*|deliv\w*|duree\s+de\s+validite)\b")


def _date_hors_autorisation(date_str: str, src: str) -> bool:
    """Vrai si la phrase qui contient la date parle de circulation / stationnement /
    travaux et PAS d'autorisation (date de restriction de circulation, de chantier…)."""
    def _n(t):
        t = unicodedata.normalize("NFKD", t or "")
        return "".join(c for c in t if not unicodedata.combining(c)).lower()
    jetons = re.findall(r"[a-z0-9]+", _n(date_str))
    if not jetons:
        return False
    texte = _n(src)
    m = re.search(r"\W*".join(re.escape(j) for j in jetons), texte)
    if not m:
        return False
    debut = max(texte.rfind(".", 0, m.start()), texte.rfind(";", 0, m.start()),
                texte.rfind("\n\n", 0, m.start()), m.start() - 300)
    fin = [x for x in (texte.find(".", m.end()), texte.find(";", m.end())) if x != -1]
    phrase = texte[debut + 1: min(fin + [m.end() + 200])]
    if _CTX_CIRCULATION_RE.search(phrase) and not _CTX_AUTORISATION_RE.search(phrase):
        return True
    # Juste avant la date (même proposition) : « début des travaux : », « les travaux
    # commenceront le », « chantier du »… sans mot d'autorisation entre les deux.
    gauche = texte[max(0, m.start() - 100): m.start()]
    gauche = re.split(r"[.;\n]\s*(?=\S)", gauche)[-1] if re.search(r"[.;]", gauche) else gauche
    return bool(_CTX_TRAVAUX_AVANT_RE.search(gauche)) and not _CTX_AUTORISATION_RE.search(gauche)


@trace_step('section', 'full_text')
def llm_extract_dates(section, client, deployment, full_text=None, debug: bool = False) -> str:
    section_str = _to_str(section).strip()
    full_text_str = _to_str(full_text).strip() if full_text is not None else section_str
    has_section = bool(section_str)

    section_str = _fix_ocr_text(_fix_broken_dates(section_str))
    full_text_str = _fix_ocr_text(_fix_broken_dates(full_text_str))

    verbatim_src_all = ((full_text_str or "") + "\n" + (section_str or "")).replace("\u00A0", " ")
    raw_src_all = verbatim_src_all

    fallback_base = section_str if has_section and section_str else full_text_str
    fallback_base = _remove_legal_reference_noise(fallback_base)
    fallback_src = fallback_base.replace("\u00A0", " ")

    system_dates = (
        "Tu extrais des dates depuis des textes administratifs français (OCR, parfois bruité).\n"
        "Tu cherches UNIQUEMENT les dates liées à l'AUTORISATION / PERMISSION / OCCUPATION DU DOMAINE PUBLIC.\n\n"
        "DEUX CHAMPS À REMPLIR :\n"
        "- Date de début d'autorisation\n"
        "- Date de fin d'autorisation\n\n"
        "RÈGLES SIMPLES :\n"
        "1) Tout ce qui suit 'jusqu'au', 'expire le', 'échéance le', 'expiration le' = DATE DE FIN.\n"
        "2) Tout ce qui suit 'à compter du', 'à partir du', 'prenant effet le' = DATE DE DÉBUT.\n"
        "3) 'du [date1] au [date2]' = début + fin (SAUF si contexte travaux/chantier).\n"
        "4) Une DURÉE (3 ans, 6 mois, 15 jours) n'est PAS une date. Ne la retourne jamais.\n"
        "5) Copie la date EXACTEMENT telle qu'elle est écrite. Ne reformate pas.\n"
        "6) Si pas de date trouvée → 'non trouvee'.\n\n"
        "DATES À IGNORER :\n"
        "- Dates dans les clauses 'Vu ...' (références juridiques)\n"
        "- Dates de signature\n"
        "- Dates de protocole, avenant, délibération, décret, loi, convention\n"
        "- Dates de travaux / chantier / intervention / durée du chantier\n"
        "- Dates de restriction de la circulation ou du stationnement des véhicules "
        "('la circulation pourra être restreinte entre le … et le …')\n"
        "- Dates de publication au journal officiel\n\n"
        "OCR :\n"
        "- 'jusqu au' = 'jusqu'au'\n"
        "- '3 1 décembre 2030' = '31 décembre 2030'\n"
    )

    prompt_dates_core = (
        "Extrais les dates d'autorisation/permission/occupation du texte ci-dessus.\n\n"
        "FORMAT DE SORTIE OBLIGATOIRE (rien d'autre) :\n"
        "<r>\n"
        "Date de debut d'autorisation : <date | non trouvee>\n"
        "Date de fin d'autorisation : <date | non trouvee>\n"
        "</r>\n"
        "REGLES STRICTES\n"
        "- Copier la date telle qu'elle apparait dans le texte.\n"
        "- Ne jamais reformuler.\n"
        "- Ne jamais calculer une date a partir d'une duree.\n"
        "- Ne jamais retourner une duree.\n"
        "- Ne jamais utiliser une date de signature.\n"
        "- Ne jamais utiliser une date provenant d'un protocole, avenant, deliberation, decret, loi, convention ou autre reference juridique.\n\n"
        "FORMATS ACCEPTES\n"
        "- JJ/MM/AAAA\n"
        "- JJ mois AAAA\n"
        "- mois AAAA\n\n"
        "IMPORTANT\n"
        "- Ne rien ajouter avant ou apres <r> ... </r>\n"
        "- Ne pas expliquer ton raisonnement\n"
    )

    if has_section:
        user_msg = f"SECTION -- lignes numerotees:\n{_numbered(section_str, 'S')}\n\n{prompt_dates_core}"
    else:
        user_msg = f"TEXTE COMPLET -- lignes numerotees:\n{_numbered(full_text_str, 'T')}\n\n{prompt_dates_core}"

    block = _run_llm(client, deployment, system_dates, user_msg, max_new_tokens=4000, debug=debug)

    deb = fin = "non trouvee"
    for line in block.splitlines():
        L = line.strip()
        Llow = L.lower()
        if "date de debut" in Llow and "autorisation" in Llow:
            deb = L.split(":", 1)[1].strip() if ":" in L else deb
        elif "date de fin" in Llow and "autorisation" in Llow:
            fin = L.split(":", 1)[1].strip() if ":" in L else fin

    deb = _hard_date_filter(deb)
    fin = _hard_date_filter(fin)

    if deb != "non trouvee" and not _is_verbatim_in(verbatim_src_all, deb):
        deb = "non trouvee"
    if fin != "non trouvee" and not _is_verbatim_in(verbatim_src_all, fin):
        fin = "non trouvee"

    MONTHS = r"(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)"
    DATE_SLASH = r"[0-3]?\d\s*/\s*[01]?\d\s*/\s*\d{2,4}"
    DATE_DMY = rf"[0-3]?\d(?:\s*er)?\s+{MONTHS}\s+\d{{4}}"
    DATE_MY = rf"{MONTHS}\s+\d{{4}}"
    DATE_ANY = rf"(?:{DATE_SLASH}|{DATE_DMY}|{DATE_MY})"

    RE_RANGE = re.compile(
        rf"(?:\bdu|\bentre\s+le)\s+(?P<d1>{DATE_ANY})\s+"
        rf"(?:\bau|\ba|\bjusqu(?:'|'|\s)?au|\bet\s+le)\s+"
        rf"(?P<d2>{DATE_ANY})",
        re.I | re.U | re.S
    )

    m_rng = RE_RANGE.search(fallback_src)
    if m_rng:
        d1 = m_rng.group("d1").strip()
        d2 = m_rng.group("d2").strip()
        deb, fin = d1, d2

    if fin == "non trouvee":
        RE_EXPIRE_DIRECT = re.compile(
            rf"(?:\bdate\s+d['']?\s*expiration\b|\bexpiration\b)\s*:?\s*(?:le\s*)?(?P<d>{DATE_ANY})",
            re.I | re.U | re.S
        )
        m_exp = RE_EXPIRE_DIRECT.search(fallback_src)
        if m_exp:
            fin = m_exp.group("d").strip()

    if fin == "non trouvee":
        DATE_DMY_PUNCT_RE = re.compile(
            r"(?:\bdate\s+d['']?\s*expiration\b|\bexpiration\b)\s*:?\s*(?:le\s*)?"
            r"(?P<d>[0-3]?\d(?:\s*er)?\s*[.\-\/]\s*"
            rf"{MONTHS}"
            r"\s*[.\-\/]\s*\d{4})",
            re.I | re.U | re.S
        )
        m_exp2 = DATE_DMY_PUNCT_RE.search(fallback_src)
        if m_exp2:
            fin = m_exp2.group("d").strip()

    if deb == "non trouvee" and not m_rng:
        anchors_deb = [
            r"\b(?:a)\s+compter\s+d(?:u|e)\b",
            r"\b(?:a)\s+partir\s+du\b"
        ]
        found_deb = _find_next_date_after_contextual(
            anchors=anchors_deb, text=fallback_src, lookahead=240, mode="start", debug=debug
        )
        if found_deb:
            deb = found_deb

    if fin == "non trouvee" and not m_rng:
        anchors_fin = [
            r"jusqu(?:'|'|\s)?au",
            r"\bvalable\s+jusqu",
            r"\bexpire\s+le",
            r"\bexpiration\s*le",
            r"\becheance\s*le"
        ]
        found_fin = _find_next_date_after_contextual(
            anchors=anchors_fin, text=fallback_src, lookahead=70, mode="end", debug=debug
        )
        if found_fin:
            fin = found_fin

    if fin == "non trouvee":
        fin_broken = _search_broken_fin(fallback_src)
        if fin_broken:
            fin = fin_broken

    if fin == "non trouvee":
        fin_ml = _extract_end_date_multiline(fallback_src, lookahead_year=200, debug=debug)
        if fin_ml:
            fin = fin_ml

    norm_all = _strip_accents(_norm_for_match(fallback_src))

    def _classify_anchor_around_date(date_str: str):
        if not date_str or date_str.lower().startswith("non trouv"):
            return None
        nd = _strip_accents(_norm_for_match(date_str))
        idx = norm_all.find(nd)
        if idx == -1:
            return None
        left = norm_all[max(0, idx - 120): idx]
        if (
            re.search(r"jusqu\s*['']?\s*au", left) or
            re.search(r"\bvalable\s+jusqu", left) or
            re.search(r"\bexpire\s+le", left) or
            re.search(r"\bexpiration\s*le", left) or
            re.search(r"\becheance\s*le", left)
        ):
            return "end"
        if (
            re.search(r"\ba\s+compter\s+d(?:u|e)\b", left) or
            re.search(r"\ba\s+partir\s+du\b", left)
        ):
            return "start"
        return None

    if deb != "non trouvee" and fin == "non trouvee":
        cls = _classify_anchor_around_date(deb)
        if cls == "end":
            fin, deb = deb, "non trouvee"

    if fin != "non trouvee" and deb == "non trouvee":
        cls = _classify_anchor_around_date(fin)
        if cls == "start":
            deb, fin = fin, "non trouvee"

    if deb != "non trouvee" and fin != "non trouvee" and _norm_for_match(deb) == _norm_for_match(fin):
        cls = _classify_anchor_around_date(deb)
        if cls == "end":
            deb = "non trouvee"
        else:
            fin = "non trouvee"

    DATE_DMY_PUNCT_VU = re.compile(
        rf"[0-3]?\d(?:\s*er)?\s*[.\-\/]\s*{MONTHS}\s*[.\-\/]\s*\d{{4}}",
        re.I | re.U
    )
    RE_VU_CLAUSE = re.compile(r"(?mi)^[\s\-\u2013\u2014\u2022\*]*vu\b.*?(?:;|\n{2,}|$)", re.S)

    vu_dates_norm = set()
    for m in RE_VU_CLAUSE.finditer(raw_src_all):
        frag = m.group(0)
        for rx in (
            re.compile(DATE_SLASH, re.I | re.U),
            re.compile(DATE_DMY, re.I | re.U),
            DATE_DMY_PUNCT_VU,
            re.compile(DATE_MY, re.I | re.U)
        ):
            for dm in rx.finditer(frag):
                vu_dates_norm.add(_norm_for_match(dm.group(0)))

    if deb != "non trouvee" and _norm_for_match(deb) in vu_dates_norm:
        deb = "non trouvee"
    if fin != "non trouvee" and _norm_for_match(fin) in vu_dates_norm:
        fin = "non trouvee"

    # Une date dont la phrase parle de circulation / stationnement / travaux, sans parler
    # d'autorisation, n'est pas une date d'autorisation
    # (« la circulation des véhicules pourra être restreinte … entre le 01 avril 2019 et le … »).
    if deb != "non trouvee" and _date_hors_autorisation(deb, raw_src_all):
        deb = "non trouvee"
    if fin != "non trouvee" and _date_hors_autorisation(fin, raw_src_all):
        fin = "non trouvee"

    if deb != "non trouvee":
        deb = _complete_year_if_missing(deb, raw_src_all, lookahead=140)
    if fin != "non trouvee":
        fin = _complete_year_if_missing(fin, raw_src_all, lookahead=140)

    deb = _dedup_month_word(deb)
    fin = _dedup_month_word(fin)

    d_deb = _parse_date_to_comparable(deb)
    d_fin = _parse_date_to_comparable(fin)
    if d_deb and d_fin and d_fin < d_deb:
        deb, fin = fin, deb

    return (
        f"Date de debut d'autorisation : {deb}\n"
        f"Date de fin d'autorisation : {fin}"
    )


def _parse_dates_output(s: str):
    deb = fin = "non trouvee"
    for line in s.splitlines():
        L = line.strip()
        Llow = L.lower()
        if "date de debut" in Llow and "autorisation" in Llow:
            deb = L.split(":", 1)[1].strip() if ":" in L else deb
        elif "date de fin" in Llow and "autorisation" in Llow:
            fin = L.split(":", 1)[1].strip() if ":" in L else fin
    return deb, fin


def dates_to_df(output: str, none_for_missing=False) -> pd.DataFrame:
    deb, fin = _parse_dates_output(output)
    if none_for_missing:
        deb = None if deb and deb.lower().startswith("non trouv") else deb
        fin = None if fin and fin.lower().startswith("non trouv") else fin
    return pd.DataFrame(
        [[deb, fin]],
        columns=["Date de debut d'autorisation", "Date de fin d'autorisation"]
    )


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .duree import _strip_accents  # noqa: E402,F401