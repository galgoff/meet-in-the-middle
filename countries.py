"""
countries.py — a curated, disclosed list of country names for validating
the nationality field in intake.py.

This is NOT pulled from an authoritative source (no ISO-3166 library and
no reliable network path to fetch one in this environment) — it's a
manually curated list of commonly used English country names, built the
same way ground_travel.py's border rules are: good enough to catch
obvious garbage input ("Googoo") without silently rejecting a real
country nobody thought to add. If a legitimate country gets rejected,
add it to KNOWN_COUNTRIES or COUNTRY_ALIASES below — don't work around
this module instead.
"""

KNOWN_COUNTRIES = {
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
    "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados",
    "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia", "Cameroon",
    "Canada", "Central African Republic", "Chad", "Chile", "China",
    "Colombia", "Comoros", "Congo", "Democratic Republic of the Congo",
    "Costa Rica", "Cote d'Ivoire", "Croatia", "Cuba", "Cyprus",
    "Czech Republic", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador",
    "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia",
    "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany",
    "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau",
    "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica",
    "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kosovo",
    "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho",
    "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg",
    "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta",
    "Marshall Islands", "Mauritania", "Mauritius", "Mexico",
    "Micronesia", "Moldova", "Monaco", "Mongolia", "Montenegro",
    "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal",
    "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria",
    "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan",
    "Palau", "Palestine", "Panama", "Papua New Guinea", "Paraguay",
    "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania",
    "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Vincent and the Grenadines", "Samoa", "San Marino",
    "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia",
    "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia",
    "Solomon Islands", "Somalia", "South Africa", "South Korea",
    "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden",
    "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago",
    "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States",
    "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela",
    "Vietnam", "Yemen", "Zambia", "Zimbabwe",
}

# Common alternate names/abbreviations people actually type, mapped to
# the canonical spelling stored above. Matching is case-insensitive, so
# each variant only needs to appear once here regardless of casing.
COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States",
    "u.s.a.": "United States", "united states of america": "United States",
    "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "britain": "United Kingdom",
    "great britain": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "uae": "United Arab Emirates", "emirates": "United Arab Emirates",
    "korea, south": "South Korea", "republic of korea": "South Korea",
    "korea, north": "North Korea", "dprk": "North Korea",
    "russian federation": "Russia",
    "ivory coast": "Cote d'Ivoire", "côte d'ivoire": "Cote d'Ivoire",
    "czechia": "Czech Republic",
    "holland": "Netherlands",
    "burma": "Myanmar",
    "drc": "Democratic Republic of the Congo",
    "congo-kinshasa": "Democratic Republic of the Congo",
    "congo-brazzaville": "Congo",
    "vatican": "Vatican City", "holy see": "Vatican City",
    "macedonia": "North Macedonia",
    "cape verde": "Cabo Verde",
    "swaziland": "Eswatini",
    "east timor": "Timor-Leste",
}


def normalize_country(raw: str) -> str | None:
    """Case-insensitive lookup against KNOWN_COUNTRIES and
    COUNTRY_ALIASES. Returns the canonical name, or None if nothing
    matches — the caller decides what to do with a non-match (intake.py
    re-prompts; nothing here assumes an interactive context)."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    for country in KNOWN_COUNTRIES:
        if country.lower() == lowered:
            return country
    return COUNTRY_ALIASES.get(lowered)
