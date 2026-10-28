"""Colonnes « Modalités de renouvellement / résiliation ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         MODALITÉS
# ====================================================================
@trace_step('section', 'full_text')
def prompt_modalites_renouvellement_resiliation(section, client, deployment, full_text=None, debug: bool = False) -> str:

    def _to_str(x):
        if x is None: return ""
        if isinstance(x, list): return "\n".join(str(s) for s in x if s)
        return str(x)

    def _numbered(s: str, prefix: str) -> str:
        lines = (s or "").splitlines()
        return "\n".join(f"{prefix}{i+1:04d}: {l}" for i, l in enumerate(lines))

    def _norm_text_basic(s: str) -> str:
        if not s: return ""
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return s

    def _lower_noacc(s: str) -> str:
        return _norm_text_basic(s).lower()

    WORD_NUM = {
        "zero":0, "zéro":0, "un":1, "une":1, "deux":2, "trois":3, "quatre":4, "cinq":5,
        "six":6, "sept":7, "huit":8, "neuf":9, "dix":10, "onze":11, "douze":12, "treize":13,
        "quatorze":14, "quinze":15, "seize":16, "dix-sept":17, "dix sept":17,
        "dix-huit":18, "dix huit":18, "dix-neuf":19, "dix neuf":19, "vingt":20,
        "trente":30, "quarante":40, "cinquante":50, "soixante":60
    }

    def _to_int_if_number_token(tok: str):
        t = _lower_noacc(tok).strip()
        t = "".join(ch for ch in t if ch.isalnum() or ch in ("-", " "))
        if t.isdigit():
            try:
                return int(t)
            except:
                return None
        if t.endswith("mois"):
            core = t[:-4].strip()
            if core in WORD_NUM:
                return WORD_NUM[core]
        if t.endswith("jours") or t.endswith("jour"):
            core = t[:-5].strip() if t.endswith("jours") else t[:-4].strip()
            if core in WORD_NUM:
                return WORD_NUM[core]
        if t in WORD_NUM:
            return WORD_NUM[t]
        if " " in t:
            parts = [p for p in t.split(" ") if p]
            if all(p in WORD_NUM for p in parts):
                val = 0
                for p in parts:
                    val += WORD_NUM[p]
                return val if val > 0 else None
        return None

    def _tokenize_soft(s: str):
        s = _lower_noacc(s)
        for ch in [",", ";", ":", "(", ")", "\t", "\r", "\xa0"]:
            s = s.replace(ch, " ")
        s = s.replace("\n", " ")
        while "  " in s:
            s = s.replace("  ", " ")
        return [w for w in s.split(" ") if w]

    def _join(tokens):
        return " ".join(tokens)

    section_str   = _to_str(section).strip()
    full_text_str = _to_str(full_text).strip() if (full_text is not None) else section_str
    has_section   = bool(section_str)
    scope_llm     = section_str if has_section else full_text_str

    system_modalites = (
        "Tu es un extracteur STRICT. Aucune inférence. Aucun calcul. "
        "Rends UNIQUEMENT le bloc <result> au format exact, sans aucun autre texte. "
        "N'extrais une valeur que si les ANCRES OBLIGATOIRES du champ sont présentes."
    )

    prompt_core = """
    RÈGLES STRICTES - PRIORITÉS + ANCRES OBLIGATOIRES

🔹 CHAMP « Modalités de renouvellement »
→ Contexte requis : la phrase/ligne doit contenir une ancre de renouvellement :
   « renouvel », « reconduct », « prorogation » (insensible à la casse, tolère OCR).

→ PRIORITÉ D'EXTRACTION (appliquer dans l'ordre, stop à la première correspondance) :
   1) [PRIORITAIRE] « X mois avant la date d'expiration »
      - X en chiffres ou lettres → TOUJOURS convertir en chiffre (ex: "deux" → "2")
      - Synonymes admis pour "expiration" : échéance, terme, fin de contrat, fin de bail
      - Sortie normalisée : "X mois avant la date d'expiration"
   2) [SECONDAIRE] « X jours avant la date d'expiration »
      - Même règles → Sortie : "X jours avant la date d'expiration"
   3) [TERTIAIRE] Si texte mentionne explicitement "tacite" (sans négation) → "tacite"
   4) [TERTIAIRE] Si texte mentionne explicitement "non tacite" / "ne...pas tacite" → "non tacite"
   5) [FALLBACK] Si aucune ancre ou aucune forme ci-dessus → "Non trouvé"

🔹 CHAMP « Modalités de résiliation »
→ Contexte requis : la phrase/ligne doit contenir une ancre de résiliation :
   « résili », « resili », « révoca », « revoca », « mettre fin », « dénonciation », « rupture »

→ PRIORITÉ D'EXTRACTION (appliquer dans l'ordre, stop à la première correspondance) :
   1) [PRIORITAIRE] « préavis de X mois » / « X mois de préavis » / « dans un délai de X mois »
      - X en chiffres ou lettres → TOUJOURS convertir en chiffre
      - Sortie normalisée : "X mois"
   2) [SECONDAIRE] Même forme avec « jours » → Sortie : "X jours"
   3) [FALLBACK] Si aucune ancre ou aucune forme ci-dessus → "Non trouvé"

🔹 RÈGLES GÉNÉRALES
- Nombres : toujours en chiffres arabes ("trente" → "30", "DEUX" → "2")
- Négations : "ne...pas tacite", "non renouvelable tacitement" → prioriser "non tacite"
- Fourchettes ("1 à 3 mois") → prendre la valeur minimale ("1 mois")

🔹 FORMAT DE SORTIE EXACT (et RIEN D'AUTRE) :
<result>
Modalités de renouvellement : <2 mois avant la date d'expiration | 2 jours avant la date d'expiration | tacite | non tacite | Non trouvé>
Modalités de résiliation : <X mois | X jours | Non trouvé>
</result>

⚠️ Si tu ne trouves aucune ancre valide pour un champ, mets impérativement "Non trouvé".
⚠️ Ne jamais ajouter de texte avant ou après le bloc <result>.
""".strip()

    user_msg = f"""
TEXTE — lignes numérotées:
{_numbered(scope_llm, "S" if has_section else "T")}

{prompt_core}
""".strip()

    def _run_llm(system_msg: str, user_msg: str) -> str:
        try:
            response = traced_completion(client.chat.completions.create, 
                model=deployment,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_completion_tokens=4000,  # GPT-5 : inclut les tokens de réflexion (était 600)
            )
            decoded = (response.choices[0].message.content or "").strip()
            if debug:
                print("DEBUG LLM RAW >>>", decoded[:2000], "<<< END")
            return decoded
        except Exception as e:
            print(f"[prompt_modalites_renouvellement_resiliation] Azure OpenAI error: {e}")
            return "non trouvées"

    raw = _run_llm(system_modalites, user_msg)

    def _extract_result_block(decoded: str) -> str:
        low = decoded.lower()
        if "<result>" in low and "</result>" in low:
            part = decoded.split("<result>", 1)[1]
            body = part.split("</result>", 1)[0]
            return "<result>\n" + body.strip() + "\n</result>"
        return decoded.strip()

    llm_result = _extract_result_block(raw)

    text_all = _lower_noacc(full_text_str if full_text_str else section_str)
    tokens = _tokenize_soft(text_all)

    def _find_token_indices_any(substr_list):
        idxs = []
        for sub in substr_list:
            s = _lower_noacc(sub)
            for i, tk in enumerate(tokens):
                if s in tk:
                    idxs.append(i)
        return sorted(set(idxs))

    def _window(tokens, center, radius):
        a = max(0, center - radius)
        b = min(len(tokens), center + radius + 1)
        return tokens[a:b]

    def _num_from_token(tk: str):
        return _to_int_if_number_token(tk)

    def _anchored_renewal_extract(radius=30):
        renew_idxs = _find_token_indices_any(["renouvel"])
        if not renew_idxs:
            return "non trouvées"

        KEY_EXP = ("expiration", "date", "echeance", "échéance", "terme")

        for anchor in renew_idxs:
            win = _window(tokens, anchor, radius)

            for i, tk in enumerate(win):
                if tk.startswith("avan"):
                    before = win[max(0, i-4):i]
                    for j in range(len(before)-1):
                        n = _num_from_token(before[j])
                        if n is not None:
                            unit = before[j+1] if j+1 < len(before) else ""
                            unit = "jours" if unit == "jour" and n > 1 else unit
                            if unit in ("mois", "jour", "jours"):
                                after = win[i:i+7]
                                after_str = " ".join(after)
                                if any(k in after_str for k in KEY_EXP):
                                    return f"{n} {unit} avant la date d'expiration"

        tacite_seen = False
        for anchor in renew_idxs:
            win = _window(tokens, anchor, radius)
            win_str = _join(win)

            if ("n'est pas tacite" in win_str) or ("non tacite" in win_str) or ("pas de renouvellement tacite" in win_str):
                return "non tacite"
            if "tacite" in win_str:
                tacite_seen = True

        if tacite_seen:
            return "tacite"

        return "Non trouvé"

    def _anchored_resiliation_extract(radius=30):
        anchors = _find_token_indices_any(
            ["résili", "resili", "résial", "resial", "révoca", "revoca", "denonci", "dénonci"]
        )
        for i in range(len(tokens)-1):
            if tokens[i] == "mettre" and tokens[i+1] == "fin":
                anchors.append(i)

        if not anchors:
            return "Non trouvé"

        for pos in anchors:
            a = max(0, pos-20)
            b = min(len(tokens), pos+25)
            window = tokens[a:b]
            for j in range(len(window)-1):
                n = _num_from_token(window[j])
                if n is not None:
                    unit = window[j+1]
                    unit = "jours" if unit == "jour" and n > 1 else unit
                    if unit in ("mois", "jour", "jours"):
                        return f"{n} {unit}"
            for j in range(len(window)-3):
                if window[j] in ("delai", "délai"):
                    if window[j+1] in ("d", "d'", "d’", "de"):
                        if window[j+2] in ("un","une"):
                            unit = window[j+3] if j+3 < len(window) else ""
                            unit = "jours" if unit == "jour" else unit
                            if unit in ("mois", "jours"):
                                return f"1 {unit}"
                        else:
                            unit = window[j+2]
                            if unit in ("mois", "jour", "jours"):
                                unit = "jours" if unit == "jour" else unit
                                return f"1 {unit}"
        return "Non trouvé"

    def _parse_llm_fields(llm_block: str):
        body = llm_block.strip().splitlines()
        renouv_val, resili_val = None, None
        for ln in body:
            s = ln.strip()
            low = _lower_noacc(s)
            if low.startswith("modalites de renouvellement"):
                val = s.split(":", 1)[1].strip() if ":" in s else ""
                renouv_val = val or renouv_val
            elif low.startswith("modalites de resiliation") or low.startswith("modalites de resialisation"):
                val = s.split(":", 1)[1].strip() if ":" in s else ""
                resili_val = val or resili_val
        return (renouv_val or "Non trouvé", resili_val or "Non trouvé")

    renouv_anchor = _anchored_renewal_extract(radius=30)
    resili_anchor = _anchored_resiliation_extract(radius=30)
    renouv_llm, resili_llm = _parse_llm_fields(llm_result)

    has_ren_anchor = bool(_find_token_indices_any(["renouvel"]))
    if renouv_anchor and not renouv_anchor.lower().startswith("non trouv"):
        renouv = renouv_anchor
    elif has_ren_anchor and (renouv_llm and not renouv_llm.lower().startswith("non trouv")):
        renouv = renouv_llm
    else:
        renouv = "Non trouvé"

    res_anchors_exist = bool(_find_token_indices_any(
        ["résili", "resili", "résial", "resial", "révoca", "revoca", "denonci", "dénonci"]
    ) or any(tokens[i] == "mettre" and tokens[i+1] == "fin" for i in range(len(tokens)-1)))

    def _looks_like_delay(v: str) -> bool:
        vlow = _lower_noacc(v)
        parts = vlow.split()
        if len(parts) == 2 and parts[1] in ("mois","jour","jours"):
            try:
                int(parts[0])
                return True
            except:
                return parts[0] in WORD_NUM
        return False

    if resili_anchor and not resili_anchor.lower().startswith("non trouv"):
        resili = resili_anchor
    elif res_anchors_exist and resili_llm and _looks_like_delay(resili_llm):
        parts = _lower_noacc(resili_llm).split()
        n = parts[0]
        unit = parts[1]
        if not n.isdigit() and n in WORD_NUM:
            n = str(WORD_NUM[n])
        if unit == "jour" and n != "1":
            unit = "jours"
        resili = f"{n} {unit}"
    else:
        resili = "Non trouvé"

    rs_low = _lower_noacc(resili)
    if "avant" in rs_low and any(k in rs_low for k in ("expiration","echeance","date","terme")):
        resili = "Non trouvé"

    return (
        "<result>\n"
        f"Modalités de renouvellement : {renouv}\n"
        f"Modalités de résiliation : {resili}\n"
        "</result>"
    )


def _parse_modalites_output(s: str):
    m = re.search(r"<result>(.*?)</result>", s, flags=re.I|re.S)
    body = (m.group(1) if m else s).strip()

    renouv = "Non trouvé"
    resili = "Non trouvé"

    for line in body.splitlines():
        raw = line.strip()
        low = _strip_accents(raw).lower()
        if low.startswith("modalites de renouvellement"):
            parts = raw.split(":", 1)
            if len(parts) > 1:
                renouv = parts[1].strip() or renouv
        elif low.startswith("modalites de resiliation"):
            parts = raw.split(":", 1)
            if len(parts) > 1:
                resili = parts[1].strip() or resili
    return renouv, resili


def modalites_to_df(output: str, none_for_missing=False) -> pd.DataFrame:
    renouv, resili = _parse_modalites_output(output)
    if none_for_missing:
        renouv = None if renouv.lower().startswith("non trouv") else renouv
        resili = None if resili.lower().startswith("non trouv") else resili
    return pd.DataFrame(
        [[renouv, resili]],
        columns=["Modalités de renouvellement", "Modalités de résiliation"]
    )


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .duree import _strip_accents  # noqa: E402,F401
