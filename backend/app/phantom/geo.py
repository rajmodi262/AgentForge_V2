"""Offline gazetteer of data-centre locations (city → state, country, lat, lon).

Kept offline on purpose: no geocoding API calls, no rate limits, deterministic
results. Aliases map the spellings news articles use to one canonical place.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# canonical: (state, country, lat, lon, [aliases])
PLACES = {
    # Malaysia
    "Johor Bahru": ("Johor", "Malaysia", 1.4927, 103.7414, ["johor bahru", "jb", "johor baru", "ulu tiram", "tebrau"]),
    "Kulai": ("Johor", "Malaysia", 1.6561, 103.6032, ["kulai", "kulaijaya"]),
    "Sedenak": ("Johor", "Malaysia", 1.6870, 103.5460, ["sedenak", "sedenak tech park", "stp"]),
    "Iskandar Puteri": ("Johor", "Malaysia", 1.4250, 103.6420, ["iskandar puteri", "nusajaya", "iskandar"]),
    "Pasir Gudang": ("Johor", "Malaysia", 1.4700, 103.9030, ["pasir gudang"]),
    "Kluang": ("Johor", "Malaysia", 2.0251, 103.3328, ["kluang"]),
    "Johor": ("Johor", "Malaysia", 1.8550, 103.5000, ["johor"]),
    "Cyberjaya": ("Selangor", "Malaysia", 2.9213, 101.6559, ["cyberjaya"]),
    "Kuala Lumpur": ("Kuala Lumpur", "Malaysia", 3.1390, 101.6869, ["kuala lumpur", "kl"]),
    "Selangor": ("Selangor", "Malaysia", 3.0738, 101.5183, ["selangor", "shah alam", "petaling jaya", "puchong", "rawang", "bukit jalil", "klang"]),
    "Negeri Sembilan": ("Negeri Sembilan", "Malaysia", 2.7258, 101.9424, ["negeri sembilan", "nilai", "seremban", "port dickson"]),
    "Kulim": ("Kedah", "Malaysia", 5.3650, 100.5617, ["kulim"]),
    "Penang": ("Penang", "Malaysia", 5.4141, 100.3288, ["penang", "batu kawan"]),
    # India
    "Navi Mumbai": ("Maharashtra", "India", 19.0330, 73.0297, ["navi mumbai", "panvel", "airoli", "mahape", "rabale", "ghansoli"]),
    "Mumbai": ("Maharashtra", "India", 19.0760, 72.8777, ["mumbai", "bombay", "chandivali", "powai", "bkc", "thane", "bhiwandi", "palava", "dombivli"]),
    "Pune": ("Maharashtra", "India", 18.5204, 73.8567, ["pune", "chakan", "talegaon", "hinjewadi"]),
    "Chennai": ("Tamil Nadu", "India", 13.0827, 80.2707, ["chennai", "ambattur", "siruseri", "sriperumbudur", "oragadam", "kanchipuram"]),
    "Hyderabad": ("Telangana", "India", 17.3850, 78.4867, ["hyderabad", "shamshabad", "medchal", "gachibowli"]),
    "Noida": ("Uttar Pradesh", "India", 28.5355, 77.3910, ["noida", "greater noida", "yamuna expressway"]),
    "Delhi NCR": ("Delhi", "India", 28.6139, 77.2090, ["delhi", "new delhi", "gurugram", "gurgaon", "ncr", "faridabad"]),
    "Bengaluru": ("Karnataka", "India", 12.9716, 77.5946, ["bengaluru", "bangalore", "whitefield"]),
    "Kolkata": ("West Bengal", "India", 22.5726, 88.3639, ["kolkata", "calcutta", "new town", "rajarhat"]),
    "Visakhapatnam": ("Andhra Pradesh", "India", 17.6868, 83.2185, ["visakhapatnam", "vizag"]),
    "Ahmedabad": ("Gujarat", "India", 23.0225, 72.5714, ["ahmedabad", "gift city", "gandhinagar", "dholera"]),
    "Jamnagar": ("Gujarat", "India", 22.4707, 70.0577, ["jamnagar"]),
    "Lucknow": ("Uttar Pradesh", "India", 26.8467, 80.9462, ["lucknow"]),
    "Kochi": ("Kerala", "India", 9.9312, 76.2673, ["kochi", "cochin"]),
    "Patna": ("Bihar", "India", 25.5941, 85.1376, ["patna", "patliputra"]),
    "Bodh Gaya": ("Bihar", "India", 24.6961, 84.9870, ["bodh gaya", "bodhgaya"]),
    "Bhubaneswar": ("Odisha", "India", 20.2961, 85.8245, ["bhubaneswar"]),
    "Jaipur": ("Rajasthan", "India", 26.9124, 75.7873, ["jaipur"]),
}

COUNTRY_CENTRE = {"Malaysia": (3.9, 102.0), "India": (21.0, 78.0)}

_ALIAS = sorted(((a, canon) for canon, v in PLACES.items() for a in v[4]), key=lambda x: -len(x[0]))


# State-level fallbacks for India: used only when no city is named anywhere ("25 acres in Andhra Pradesh").
# Kept apart from PLACES so a state name can never outrank a city in the same sentence.
STATES = {
    "Andhra Pradesh": ("Andhra Pradesh", "India", 15.9129, 79.7400, ["andhra pradesh", "anakapalli", "amaravati"]),
    "Maharashtra": ("Maharashtra", "India", 19.7515, 75.7139, ["maharashtra"]),
    "Tamil Nadu": ("Tamil Nadu", "India", 11.1271, 78.6569, ["tamil nadu"]),
    "Telangana": ("Telangana", "India", 18.1124, 79.0193, ["telangana"]),
    "Uttar Pradesh": ("Uttar Pradesh", "India", 26.8467, 80.9462, ["uttar pradesh"]),
    "Gujarat": ("Gujarat", "India", 22.2587, 71.1924, ["gujarat"]),
    "Karnataka": ("Karnataka", "India", 15.3173, 75.7139, ["karnataka"]),
    "West Bengal": ("West Bengal", "India", 22.9868, 87.8550, ["west bengal"]),
    "Odisha": ("Odisha", "India", 20.9517, 85.0985, ["odisha", "orissa"]),
    "Rajasthan": ("Rajasthan", "India", 27.0238, 74.2179, ["rajasthan"]),
}
PLACES.update({k: v for k, v in STATES.items() if k not in PLACES})
_STATE_ALIAS = sorted(((a, canon) for canon, v in STATES.items() for a in v[4]), key=lambda x: -len(x[0]))


def resolve_place(*texts: Optional[str]) -> Optional[str]:
    """First canonical place whose alias appears in any of the given strings (longest alias wins).
    Cities are tried across ALL strings before any state-level fallback."""
    lows = [(t or "").lower() for t in texts if t]
    for table in (_ALIAS, _STATE_ALIAS):
        for low in lows:
            for alias, canon in table:
                if re.search(rf"\b{re.escape(alias)}\b", low):
                    return canon
    return None


_IN = re.compile(r"\bindia\b|\bindian\b|₹|\brs\.?\s?\d|\bcrore\b|\blakh\b|maharashtra|tamil nadu|telangana|uttar pradesh|karnataka", re.I)
_MY = re.compile(r"\bmalaysia\b|\bmalaysian\b|\bringgit\b|\brm\s?\d|\bjohor\b|selangor|\btnb\b|tenaga nasional|bursa", re.I)
_OTHER = re.compile(r"\b(indonesia|jakarta|batam|singapore|thailand|bangkok|vietnam|philippines|japan|australia|united states|u\.s\.|europe|finland|nurmij\w*|sweden|norway|denmark|ireland|germany|netherlands|spain|united kingdom|hong kong|china|taiwan|korea|philippine|manila|tokyo|saitama|osaka|nongsa|trinidad|tobago|seoul|pohang|sydney|melbourne|texas|virginia|oregon|ohio|arizona|wyoming|idaho|nevada|indiana|louisiana|tennessee|wisconsin|michigan|pennsylvania|new jersey|california|illinois|iowa|london|uk|france|paris|frankfurt|amsterdam|dublin|madrid|italy|milan|cordoba|argentina|brazil|chile|mexico|canada|saudi|uae|dubai|abu dhabi|qatar|africa|nigeria|kenya)\b", re.I)


def infer_country(*texts: Optional[str]) -> Optional[str]:
    """Country of a mention: a gazetteer place wins; else whichever country's signals dominate the text."""
    place = resolve_place(*texts)
    if place:
        return PLACES[place][1]
    blob = " ".join(t or "" for t in texts)
    i, m, o = len(_IN.findall(blob)), len(_MY.findall(blob)), len(_OTHER.findall(blob))
    if max(i, m) == 0 or o > max(i, m):
        return None
    return "India" if i > m else "Malaysia" if m > i else None


def coords(place: Optional[str], country: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float]]:
    if place and place in PLACES:
        st, c, lat, lon, _ = PLACES[place]
        return place, st, lat, lon
    if country in COUNTRY_CENTRE:
        lat, lon = COUNTRY_CENTRE[country]
        return None, None, lat, lon
    return None, None, None, None
