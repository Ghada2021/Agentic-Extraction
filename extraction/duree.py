"""Colonne « Durée de l'autorisation ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         SECTION (durée)
# ====================================================================
def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def extract_duree_sections_from_text(text: str, lines_after_keyword: int = 4) -> List[str]:
    """
    Retourne les blocs (X lignes) après chaque mot-clé durée/validité/cession/contrat.
    Exclut les blocs 'durée des travaux' / 'durée du chantier'.
    """
    if not text:
        return []

    orig_lines = text.splitlines()
    norm_lines = [_strip_accents(l).upper() for l in orig_lines]

    KEYWORDS = (
        "DUREE", "VALIDITE", "CESSION",
        "DATE D'EFFET - DUREE", "DATE D'EFFET - DURÉE",
        "CONTRAT",
    )

    NEGATIVE_PATTERNS = re.compile(
        r"DUREE\s+(DES?\s+)?(TRAVAUX|CHANTIER|INTERVENTION|OCCUPATION\s+DU?\s+CHANTIER|EMPRISE)"
        r"|DUREE\s+ESTIMEE\s+(DES?\s+)?(TRAVAUX|CHANTIER)"
        r"|DUREE\s+PREVUE\s+(DES?\s+)?(TRAVAUX|CHANTIER)"
        r"|DUREE\s+PREVISIONNELLE"
        r"|DUREE\s+TOTALE\s+(DES?\s+)?(TRAVAUX|CHANTIER)"
        r"|DELAI\s+(DE?\s+)?(TRAVAUX|EXECUTION|REALISATION)"
        r"|PLANNING\s+(DES?\s+)?TRAVAUX"
        r"|CALENDRIER\s+(DES?\s+)?TRAVAUX",
        re.IGNORECASE,
    )

    results = []

    for i, line in enumerate(norm_lines):
        if any(keyword in line for keyword in KEYWORDS):
            end_index = min(i + lines_after_keyword + 1, len(orig_lines))
            block_lines = orig_lines[i:end_index]
            block = "\n".join(block_lines).strip()

            if not block:
                continue

            block_norm = _strip_accents(block).upper()
            if NEGATIVE_PATTERNS.search(block_norm):
                continue

            results.append(block)

    return results


# ====================================================================
#                         DURÉE
# ====================================================================
@trace_step('section', 'full_text')
def llm_extract_duree(section, client, deployment, full_text=None, debug: bool = False) -> str:
    """Retourne : Durée de l'autorisation : <N ans|N mois|N jours|non trouvée>."""

    def _to_str(x):
        if x is None:
            return ""
        if isinstance(x, list):
            return "\n".join(str(s) for s in x if s)
        return str(x)

    def _numbered(text, tag="X"):
        lines = (text or "").splitlines()
        return "\n".join(f"[{tag}{i:03d}] {ln}" for i, ln in enumerate(lines))

    def _strip_accents_lower(s: str) -> str:
        if not s:
            return ""
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _compact(s: str) -> str:
        return re.sub(r"[\s\-_/.,;:()]+", "", _strip_accents_lower(s))

    _UNITS = {
        0: "zero", 1: "un", 2: "deux", 3: "trois", 4: "quatre",
        5: "cinq", 6: "six", 7: "sept", 8: "huit", 9: "neuf",
        10: "dix", 11: "onze", 12: "douze", 13: "treize", 14: "quatorze",
        15: "quinze", 16: "seize", 17: "dix-sept", 18: "dix-huit", 19: "dix-neuf",
    }
    _TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}

    _WORDS_TO_INT = {}
    for n, w in _UNITS.items():
        _WORDS_TO_INT[w.replace(" ", "").replace("-", "")] = n
    _WORDS_TO_INT["une"] = 1
    for t, w in _TENS.items():
        _WORDS_TO_INT[w] = t
        _WORDS_TO_INT[w.replace("-", "")] = t
        _WORDS_TO_INT[(w + " et un").replace(" ", "").replace("-", "")] = t + 1
        for u in range(2, 10):
            form = f"{w}-{_UNITS[u]}"
            _WORDS_TO_INT[form.replace(" ", "").replace("-", "")] = t + u

    def _words_to_int_fr(raw: str):
        s = _strip_accents_lower(raw)
        key = s.replace(" ", "").replace("-", "")
        return _WORDS_TO_INT.get(key)

    def _normalize_unit(u: str) -> str:
        u = _strip_accents_lower(u)
        if u.startswith("anne"):
            return "ans"
        if u.startswith("mo"):
            return "mois"
        if u.startswith("jour"):
            return "jours"
        if u.startswith("an"):
            return "ans"
        return "ans"

    _OCR_DIGIT_MAP = str.maketrans({
        "o": "0", "O": "0", "l": "1", "I": "1", "|": "1",
        "S": "5", "s": "5", "Z": "2", "z": "2",
        "B": "8", "b": "6", "Q": "0",
    })

    _NUM_TOKEN = r"(?=[0-9oOlLI|sSzZbBQ]{1,3})(?=\S*[0-9])[0-9oOlLI|sSzZbBQ]{1,3}"

    def _to_int_ocr(tok: str):
        if not re.search(r"[0-9]", tok):
            return None
        try:
            return int(tok.translate(_OCR_DIGIT_MAP))
        except Exception:
            return None

    TRIGGERS = (
        "pour une durée", "pour une duree",
        "d'une durée", "d'une duree",
        "valable pendant", "valable pour",
        "durée de l'autorisation", "duree de l'autorisation",
        "durée d'autorisation", "duree d'autorisation",
        "durée de la permission", "duree de la permission",
        "durée de la convention", "duree de la convention",
        "objet de la présente autorisation", "objet de la presente autorisation",
        "durée", "duree", "autorisation", "valable", "expire", "arrete", "arrêté",
    )

    STRONG_TRIGGERS = (
        "pour une durée", "pour une duree",
        "d'une durée", "d'une duree",
        "valable pendant", "valable pour",
        "durée de l'autorisation", "duree de l'autorisation",
        "durée d'autorisation", "duree d'autorisation",
        "durée de la permission", "duree de la permission",
        "durée de la convention", "duree de la convention",
        "pour une période", "pour une periode",
        "fixée à", "fixee a",
        "établie pour", "etablie pour",
        "accordée pour", "accordee pour",
        "consentie pour", "autorisée pour", "autorisee pour",
    )

    NEG_CONTEXT = re.compile(
        r"\b("
        r"depuis|plus\s+de|au\s+moins|min\.?|minimum|max\.?|maximum|"
        r"d[ée]lai\s+de\s+recours|delai\s+de\s+recours|recours|tribunal|contentieux|notification|"
        r"signature|page\s*\d+|^article\s*\d+|n[°oº]|"
        r"avant\s+l[''']?\s*expiration|avant\s+le\s+terme|avant\s+l[''']?\s*[ée]ch[ée]ance|"
        r"informer.*\bavant\b|pr[ée]venir.*\bavant\b|pr[ée]avis|"
        r"remise\s+en\s+[ée]tat|dans\s+le\s+d[ée]lai\s+d"
        r"|dur[ée]e\s+(?:des?\s+)?(?:travaux|chantier|intervention|emprise)"
        r"|dur[ée]e\s+estim[ée]e?\s+(?:des?\s+)?(?:travaux|chantier)"
        r"|dur[ée]e\s+pr[ée]vue?\s+(?:des?\s+)?(?:travaux|chantier)"
        r"|dur[ée]e\s+pr[ée]visionnelle"
        r"|dur[ée]e\s+totale\s+(?:des?\s+)?(?:travaux|chantier)"
        r"|d[ée]lai\s+(?:de?\s+)?(?:travaux|ex[ée]cution|r[ée]alisation)"
        r"|planning\s+(?:des?\s+)?travaux"
        r"|calendrier\s+(?:des?\s+)?travaux"
        r"|travaux\s+d'une\s+dur[ée]e"
        r"|travaux\s+pour\s+une\s+dur[ée]e"
        r"|travaux\s+estim[ée]s?\s+[àa]"
        r"|travaux\s+pr[ée]vus?\s+(?:sur|pour|pendant)"
        r"|dur[ée]e\s+approximative"
        r"|dur[ée]e\s+de\s+l['']?\s*op[ée]ration"
        r"|semaines?\s+de\s+travaux"
        r"|jours?\s+(?:ouvr[ée]s?|ouvrables?)\s+de\s+travaux"
        r")\b",
        re.I,
    )

    TRAVAUX_CONTEXT = re.compile(
        r"\b(travaux|chantier|intervention|emprise|op[ée]ration"
        r"|ex[ée]cution|r[ée]alisation|planning|calendrier)\b",
        re.I,
    )
    AUTORISATION_CONTEXT = re.compile(
        r"\b(autorisation|permission|convention|arr[êe]t[ée]|consentie"
        r"|valable|validit[ée]|pr[ée]sente?\s+autorisation"
        r"|pr[ée]sent\s+arr[êe]t[ée]|accord[ée]e?\s+pour)\b",
        re.I,
    )

    def _is_travaux_line(ln: str) -> bool:
        ln_norm = _strip_accents_lower(ln)
        has_travaux = bool(TRAVAUX_CONTEXT.search(ln_norm))
        has_autoris = bool(AUTORISATION_CONTEXT.search(ln_norm))
        if has_travaux and not has_autoris:
            return True
        return False

    _UNIT_PRIORITY = {"ans": 3, "mois": 2, "jours": 1}

    def _rank(cand):
        n, unit = cand
        return (_UNIT_PRIORITY.get(unit, 0), n)

    def _int_to_words_fr(x: int) -> str:
        if x in _UNITS:
            return _UNITS[x]
        if x in _TENS:
            return _TENS[x]
        if 20 < x < 70:
            t, u = (x // 10) * 10, x % 10
            if u == 1:
                return f"{_TENS[t]} et un"
            return f"{_TENS[t]}-{_UNITS[u]}"
        return str(x)

    def _variants_for(n: int, unit: str):
        a = f"{n} {unit}"
        b = f"{n}{unit}"
        w = _int_to_words_fr(n)
        c = f"{w} {unit}"
        d = f"{w}{unit}"
        extras = set()
        if n == 1:
            extras.add(_compact(f"une {unit}"))
            if unit == "ans":
                extras.add(_compact("une annee"))
                extras.add(_compact("un an"))
        return {_compact(a), _compact(b), _compact(c), _compact(d)} | extras

    def _line_has_trigger(s: str) -> bool:
        s = _strip_accents_lower(s)
        return any(t in s for t in TRIGGERS)

    def _line_has_strong_trigger(s: str) -> bool:
        s = _strip_accents_lower(s)
        return any(t in s for t in STRONG_TRIGGERS)

    def _line_accepts(line: str, variants_set, unit: str = "ans") -> bool:
        ln_space = _strip_accents_lower(line)
        if NEG_CONTEXT.search(ln_space):
            return False
        if _is_travaux_line(line):
            return False
        if unit in ("mois", "jours"):
            if not _line_has_strong_trigger(ln_space):
                return False
        else:
            if not _line_has_trigger(ln_space):
                return False
        ln_compact = _compact(line)
        return any(v in ln_compact for v in variants_set)

    def _parse_llm_duration(d: str):
        if not d or d.lower().startswith("non trouv"):
            return None
        m = re.search(rf"({_NUM_TOKEN})\s*(ans?|annee?s?|mois|mos|jours?)", d, flags=re.I)
        if not m:
            m2 = re.search(
                r"\b(une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|"
                r"onze|douze|treize|quatorze|quinze|seize|"
                r"vingt|trente|quarante|cinquante|soixante)\s+"
                r"(ans?|annee?s?|mois|jours?)\b",
                d, flags=re.I,
            )
            if m2:
                n = _words_to_int_fr(m2.group(1))
                if n is not None:
                    unit = _normalize_unit(m2.group(2))
                    return n, unit
            return None
        n = _to_int_ocr(m.group(1))
        if n is None:
            return None
        unit = _normalize_unit(m.group(2))
        return n, unit

    def _scan_line_for_candidates(ln_norm: str):
        cands = []
        has_strong = _line_has_strong_trigger(ln_norm)

        for m in re.finditer(
            rf"\b({_NUM_TOKEN})\s*(ans?|annee?s?|mois|mos|jours?)\b",
            ln_norm, flags=re.I,
        ):
            n = _to_int_ocr(m.group(1))
            if n is None:
                continue
            unit = _normalize_unit(m.group(2))
            if unit in ("mois", "jours") and not has_strong:
                continue
            cands.append((n, unit))

        for m in re.finditer(
            r"\b(une?|deux|trois|quatre|cinq|six|sept|huit|neuf|"
            r"dix|onze|douze|treize|quatorze|quinze|seize|"
            r"dix[ -]?sept|dix[ -]?huit|dix[ -]?neuf|"
            r"vingt(?:\s+et\s+un)?|trente(?:\s+et\s+un)?|quarante(?:\s+et\s+un)?|"
            r"cinquante(?:\s+et\s+un)?|soixante(?:\s+et\s+un)?|"
            r"vingt[ -](?:deux|trois|quatre|cinq|six|sept|huit|neuf)|"
            r"trente[ -](?:deux|trois|quatre|cinq|six|sept|huit|neuf)|"
            r"quarante[ -](?:deux|trois|quatre|cinq|six|sept|huit|neuf)|"
            r"cinquante[ -](?:deux|trois|quatre|cinq|six|sept|huit|neuf))"
            r"\s+(ans?|annee?s?|mois|mos|jours?)\b",
            ln_norm, flags=re.I,
        ):
            n = _words_to_int_fr(m.group(1))
            if n is None:
                continue
            unit = _normalize_unit(m.group(2))
            if unit in ("mois", "jours") and not has_strong:
                continue
            cands.append((n, unit))

        return cands

    def _recover_from_text(raw_text: str) -> str:
        if not raw_text:
            return ""
        lines = raw_text.splitlines()
        best = None

        for ln in lines:
            ln_norm = _strip_accents_lower(ln)
            if not _line_has_trigger(ln_norm) or NEG_CONTEXT.search(ln_norm):
                continue
            if _is_travaux_line(ln):
                continue
            for cand in _scan_line_for_candidates(ln_norm):
                if (best is None) or (_rank(cand) > _rank(best)):
                    best = cand

        if best is None:
            for i in range(len(lines) - 1):
                combo = lines[i] + " " + lines[i + 1]
                ln_norm2 = _strip_accents_lower(combo)
                if not _line_has_trigger(ln_norm2) or NEG_CONTEXT.search(ln_norm2):
                    continue
                if _is_travaux_line(combo):
                    continue
                for cand in _scan_line_for_candidates(ln_norm2):
                    if (best is None) or (_rank(cand) > _rank(best)):
                        best = cand

        if best:
            return f"{best[0]} {best[1]}"
        return ""

    def _recover_from_delai(raw_text: str) -> str:
        if not raw_text:
            return ""
        norm = _strip_accents_lower(raw_text)
        pat = re.compile(
            rf"\bd[ée]lai\s+de\s+({_NUM_TOKEN})\s*(ans?|annee?s?|mois|jours?)\b",
            re.I,
        )
        best = None
        for m in pat.finditer(norm):
            n = _to_int_ocr(m.group(1))
            if n is None:
                continue
            unit = _normalize_unit(m.group(2))
            lo = max(0, m.start() - 160)
            hi = min(len(norm), m.end() + 160)
            window = norm[lo:hi]
            if re.search(r"\b(recours|tribunal|contentieux|gracieux|notification)\b", window):
                continue
            if re.search(r"\b(travaux|chantier|intervention|execution|realisation)\b", window):
                continue
            if not re.search(
                r"\b(autorisation|presente autorisation|arrete|renouvel|valable|expire|duree)\b",
                window,
            ):
                continue
            if unit in ("mois", "jours"):
                if not any(t in window for t in (
                    "pour une duree", "pour une durée",
                    "valable pour", "valable pendant",
                    "duree de l'autorisation", "durée de l'autorisation",
                )):
                    continue
            cand = (n, unit)
            if (best is None) or (_rank(cand) > _rank(best)):
                best = cand
        return f"{best[0]} {best[1]}" if best else ""

    def _variants_ok(duree_text: str, raw_text: str) -> bool:
        parsed = _parse_llm_duration(duree_text)
        if not parsed or not raw_text:
            return False
        n, unit = parsed
        variants = _variants_for(n, unit)
        lines = (raw_text or "").splitlines()
        for ln in lines:
            if _line_accepts(ln, variants, unit=unit):
                return True
        for i in range(len(lines) - 1):
            combo = lines[i] + " " + lines[i + 1]
            if _line_accepts(combo, variants, unit=unit):
                return True
        return False

    scope = _to_str(full_text).strip() if full_text else _to_str(section).strip()

    duree = "non trouvée"

    try:
        system_duree = (
            "Tu es un extracteur ULTRA STRICT de DURÉE administrative. "
            "Réponds UNIQUEMENT en FRANÇAIS.\n"
            "\n"
            "OBJECTIF\n"
            "- Extraire UNIQUEMENT la durée explicite de validité de "
            "l'AUTORISATION / PERMISSION / CONVENTION / ARRÊTÉ.\n"
            "- La durée doit être explicitement écrite dans le texte.\n"
            "- Formats acceptés uniquement : 'N ans', 'N mois' ou 'N jours'.\n"
            "- Si la durée est écrite en lettres, convertis uniquement le nombre en chiffres.\n"
            "  Exemple : 'trois ans' → '3 ans'.\n"
            "- Si plusieurs durées sont présentes, privilégie celle explicitement liée "
            "à la VALIDITÉ de l'autorisation, permission, convention ou arrêté.\n"
            "\n"
            "INDICES POSITIFS — À PRIVILÉGIER\n"
            "- 'pour une durée de ...'\n"
            "- 'valable pour une durée de ...'\n"
            "- 'la présente autorisation est accordée pour ...'\n"
            "- 'la présente permission est consentie pour ...'\n"
            "- 'durée de validité : ...'\n"
            "- 'est délivrée pour une durée de ...'\n"
            "- 'est accordée pour une durée de ...'\n"
            "- 'pour une période de ...' uniquement si cette période désigne clairement "
            "la validité de l'autorisation et non les travaux.\n"
            "\n"
            "INTERDICTIONS ABSOLUES\n"
            "- NE JAMAIS extraire la durée des TRAVAUX, du CHANTIER, de l'INTERVENTION "
            "ou de l'OPÉRATION.\n"
            "- NE JAMAIS calculer une durée à partir d'une date de début et d'une date de fin.\n"
            "- NE JAMAIS déduire une durée à partir de deux dates.\n"
            "- IGNORER les dates JJ/MM/AAAA ou autres formats de dates.\n"
            "- IGNORER les délais de recours, contentieux, notification ou réponse.\n"
            "- IGNORER les délais de préavis.\n"
            "- IGNORER les délais de remise en état.\n"
            "- IGNORER les délais d'exécution des travaux.\n"
            "- IGNORER les délais avant commencement des travaux.\n"
            "- IGNORER les mentions de renouvellement tacite ou explicite "
            "si elles ne donnent pas directement la durée initiale de l'autorisation.\n"
            "- IGNORER les numéros d'articles, références et numéros de lignes OCR.\n"
            "\n"
            "EXEMPLES\n"
            "\n"
            "Texte : 'La présente permission est accordée pour une durée de 5 ans.'\n"
            "→ Durée de l'autorisation : 5 ans\n"
            "\n"
            "Texte : 'Les travaux auront une durée de 15 jours.'\n"
            "→ Durée de l'autorisation : non trouvée\n"
            "\n"
            "Texte : 'Autorisation valable du 01/01/2025 au 31/12/2025.'\n"
            "→ Durée de l'autorisation : non trouvée\n"
            "IMPORTANT : ne pas calculer 1 an à partir des dates.\n"
            "\n"
            "Texte : 'La convention est consentie pour trois ans.'\n"
            "→ Durée de l'autorisation : 3 ans\n"
            "\n"
            "Texte : 'Durée des travaux : 2 mois. La présente autorisation est accordée pour 5 ans.'\n"
            "→ Durée de l'autorisation : 5 ans\n"
            "\n"
            "RÈGLE DE SÉCURITÉ\n"
            "- Si la durée n'est pas explicitement reliée à l'autorisation / permission / "
            "convention / arrêté, réponds 'non trouvée'.\n"
            "- En cas d'ambiguïté entre durée des travaux et durée de l'autorisation, "
            "ne prends PAS la durée des travaux.\n"
            "\n"
            "FORMAT EXACT\n"
            "<r>\n"
            "Durée de l'autorisation : <N ans|N mois|N jours|non trouvée>\n"
            "</r>\n"
        )

        user_msg = f"""
        TEXTE À ANALYSER — lignes numérotées :

        {_numbered(scope, "X")}

        RAPPEL :
        - Extrais uniquement une durée EXPLICITEMENT écrite de validité de
        l'autorisation / permission / convention / arrêté.
        - Ne prends jamais la durée des travaux.
        - Ne calcule jamais une durée à partir de dates.

        Réponds STRICTEMENT :

        <r>
        Durée de l'autorisation : <N ans|N mois|N jours|non trouvée>
        </r>
        """.strip()

        block = _run_llm(client, deployment, system_duree, user_msg, debug=debug)

        for line in block.splitlines():
            L = line.strip()
            if _strip_accents_lower(L).startswith("duree de l'autorisation"):
                duree = L.split(":", 1)[1].strip() if ":" in L else "non trouvée"
                break

        if not duree.lower().startswith("non trouv"):
            if not _variants_ok(duree, scope):
                rec = _recover_from_text(scope) or _recover_from_delai(scope)
                duree = rec if rec else "non trouvée"

    except Exception:
        rec = _recover_from_text(scope) or _recover_from_delai(scope)
        duree = rec if rec else "non trouvée"

    return f"Durée de l'autorisation : {duree}"


def _parse_duree_output(s: str) -> str:
    m = re.search(r"<r>(.*?)</r>", s, flags=re.I | re.S)
    body = (m.group(1) if m else s).strip()
    m2 = re.search(r"Dur[ée]e\s+de\s+l'?autorisation\s*:\s*(.+)", body, flags=re.I)
    val = m2.group(1).strip() if m2 else "non trouvée"
    return val.splitlines()[0].strip()


def duree_to_df2(output: str, none_for_missing=False) -> pd.DataFrame:
    v = _parse_duree_output(output)
    if none_for_missing and v.lower().startswith("non trouv"):
        v = None
    return pd.DataFrame({"Durée de l'autorisation": [v]})


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .dates_autorisation import _run_llm  # noqa: E402,F401
