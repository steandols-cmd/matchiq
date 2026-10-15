"""Manuellt kurerade, EXAKTA lagalias.

Varje rad: (kanoniskt fullständigt namn, land, inhemsk tävlingskod, UEFA-lag-ID:n,
globala alias, källspecifika alias {källa: [alias]}).

Källspecifika alias används där en kortform är tvetydig utanför sin källa. Exempel:
UEFA:s matchdata kallar Paris Saint-Germain för "Paris" – det aliaset gäller därför
bara källan ``uefa`` och kan aldrig förväxlas med "Paris FC" i fransk ligadata.
På samma sätt finns inget alias "Slovan" (Slovan Bratislava ≠ Slovan Liberec).
"""

CL_TEAMS: list[tuple] = [
    ("AEK Athens", "GRE", None, ["50129"], ["AEK Athens"], {}),
    ("APOEL", "CYP", None, ["50118"], ["APOEL"], {}),
    ("Ajax", "NED", "NED1", ["50143"], ["Ajax", "AFC Ajax"], {}),
    ("Anderlecht", "BEL", "BEL1", ["50074"], ["Anderlecht", "RSC Anderlecht"], {}),
    ("Royal Antwerp", "BEL", "BEL1", ["50113"], ["Royal Antwerp", "Royal Antwerp FC", "Antwerp"], {}),
    ("Arsenal", "ENG", "ENG1", ["52280"], ["Arsenal", "Arsenal FC"], {}),
    ("Astana", "KAZ", None, ["2600605"], ["Astana"], {}),
    ("Aston Villa", "ENG", "ENG1", ["52683"], ["Aston Villa", "Aston Villa FC"], {}),
    ("Atalanta", "ITA", "ITA1", ["52816"], ["Atalanta", "Atalanta BC"], {}),
    ("Athletic Club", "ESP", "ESP1", ["50125"], ["Athletic Club"], {}),
    ("Atlético de Madrid", "ESP", "ESP1", ["50124"],
     ["Atlético de Madrid", "Club Atlético de Madrid", "Atletico Madrid", "Atlético Madrid", "Atleti"], {}),
    ("Austria Wien", "AUT", "AUT1", ["50110"], ["Austria Wien"], {}),
    ("Borussia Dortmund", "GER", "GER1", ["52758"], ["Borussia Dortmund", "B. Dortmund", "Dortmund"], {}),
    ("BATE Borisov", "BLR", None, ["66168"], ["BATE Borisov", "BATE"], {}),
    ("Barcelona", "ESP", "ESP1", ["50080"], ["Barcelona", "FC Barcelona"], {}),
    ("Basel", "SUI", None, ["59856"], ["Basel", "FC Basel"], {}),
    ("Bayern München", "GER", "GER1", ["50037"], ["Bayern München", "FC Bayern München", "Bayern"], {}),
    ("İstanbul Başakşehir", "TUR", "TUR1", ["2600288"], ["İstanbul Başakşehir", "Başakşehir"], {}),
    ("Benfica", "POR", "POR1", ["50147"], ["Benfica", "SL Benfica", "Sport Lisboa e Benfica"], {}),
    ("Beşiktaş", "TUR", "TUR1", ["50157"], ["Beşiktaş"], {}),
    ("Bodø/Glimt", "NOR", "NOR1", ["59333"], ["Bodø/Glimt", "FK Bodø/Glimt", "Bodo Glimt", "Bodø Glimt"], {}),
    ("Bologna", "ITA", "ITA1", ["52969"], ["Bologna", "Bologna FC 1909"], {}),
    ("Sporting Braga", "POR", "POR1", ["52336"], ["Sporting Braga", "Sporting Clube de Braga", "Braga"], {}),
    ("Stade Brestois", "FRA", "FRA1", ["2601306"], ["Stade Brestois", "Stade Brestois 29", "Brest"], {}),
    ("CFR Cluj", "ROU", None, ["88131"], ["CFR Cluj"], {}),
    ("CSKA Moskva", "RUS", None, ["54266"], ["CSKA Moskva"], {}),
    ("Celtic", "SCO", "SCO1", ["50050"], ["Celtic"], {}),
    ("Chelsea", "ENG", "ENG1", ["52914"], ["Chelsea", "Chelsea FC"], {}),
    ("Club Brugge", "BEL", "BEL1", ["50043"], ["Club Brugge", "Club Brugge KV"], {}),
    ("Como", "ITA", "ITA1", ["79946"], ["Como", "Como 1907"], {}),
    ("FC København", "DEN", None, ["52709"], ["FC København", "Copenhagen"], {}),
    ("Crvena Zvezda", "SRB", None, ["50069"], ["Crvena Zvezda"], {}),
    ("Dynamo Kyiv", "UKR", "UKR1", ["52723"], ["Dynamo Kyiv"], {}),
    ("Fenerbahçe", "TUR", "TUR1", ["52692"], ["Fenerbahçe", "Fenerbahce"], {}),
    ("Ferencváros", "HUN", None, ["52298"], ["Ferencváros"], {}),
    ("Feyenoord", "NED", "NED1", ["52749"], ["Feyenoord", "Feyenoord Rotterdam"], {}),
    ("Eintracht Frankfurt", "GER", "GER1", ["50072"], ["Eintracht Frankfurt", "Frankfurt"], {}),
    ("Dinamo Zagreb", "CRO", None, ["50164"], ["Dinamo Zagreb", "GNK Dinamo"], {}),
    ("Galatasaray", "TUR", "TUR1", ["50067"], ["Galatasaray"], {}),
    ("Genk", "BEL", "BEL1", ["61582"], ["Genk", "KRC Genk"], {}),
    ("Gent", "BEL", "BEL1", ["4608"], ["Gent", "KAA Gent"], {}),
    ("Girona", "ESP", "ESP1", ["2602798"], ["Girona", "Girona FC"], {}),
    ("TSG Hoffenheim", "GER", "GER1", ["2600431"], ["TSG Hoffenheim", "TSG 1899 Hoffenheim", "Hoffenheim"], {}),
    ("Inter", "ITA", "ITA1", ["50138"], ["Inter", "FC Internazionale Milano", "Internazionale"], {}),
    ("Juventus", "ITA", "ITA1", ["50139"], ["Juventus", "Juventus FC"], {}),
    ("Kairat Almaty", "KAZ", None, ["79970"], ["Kairat Almaty", "Kairat"], {}),
    ("Krasnodar", "RUS", None, ["2601038"], ["Krasnodar"], {}),
    ("LASK", "AUT", "AUT1", ["63405"], ["LASK"], {}),
    ("Lazio", "ITA", "ITA1", ["52973"], ["Lazio", "SS Lazio"], {}),
    ("Legia Warszawa", "POL", None, ["50146"], ["Legia Warszawa"], {}),
    ("Leicester City", "ENG", "ENG1", ["53577"], ["Leicester City", "Leicester City FC", "Leicester"], {}),
    ("RB Leipzig", "GER", "GER1", ["2603790"], ["RB Leipzig", "Leipzig"], {}),
    ("RC Lens", "FRA", "FRA1", ["52277"], ["RC Lens", "Racing Club de Lens", "Lens"], {}),
    ("Bayer Leverkusen", "GER", "GER1", ["50109"], ["Bayer Leverkusen", "Bayer 04 Leverkusen", "Leverkusen"], {}),
    ("Lille", "FRA", "FRA1", ["75797"], ["Lille", "Lille OSC"], {}),
    ("Liverpool", "ENG", "ENG1", ["7889"], ["Liverpool", "Liverpool FC"], {}),
    ("Lokomotiv Moskva", "RUS", None, ["53065"], ["Lokomotiv Moskva"], {}),
    ("Ludogorets", "BUL", None, ["2603104"], ["Ludogorets"], {}),
    ("Olympique Lyonnais", "FRA", "FRA1", ["5312"], ["Olympique Lyonnais", "Lyon"], {}),
    ("Maccabi Tel-Aviv", "ISR", None, ["57477"], ["Maccabi Tel-Aviv", "M. Tel-Aviv"], {}),
    ("Maccabi Haifa", "ISR", None, ["59045"], ["Maccabi Haifa"], {}),
    ("Malmö FF", "SWE", "SWE1", ["50152"], ["Malmö FF", "Malmö"], {}),
    ("Manchester City", "ENG", "ENG1", ["52919"], ["Manchester City", "Manchester City FC", "Man City"], {}),
    ("Manchester United", "ENG", "ENG1", ["52682"], ["Manchester United", "Manchester United FC", "Man Utd"], {}),
    ("Maribor", "SVN", None, ["57490"], ["Maribor"], {}),
    ("Olympique de Marseille", "FRA", "FRA1", ["52748"],
     ["Olympique de Marseille", "Olympique Marseille", "Marseille"], {}),
    ("Midtjylland", "DEN", None, ["75795"], ["Midtjylland"], {}),
    ("AC Milan", "ITA", "ITA1", ["50058"], ["AC Milan", "Milan"], {}),
    ("AS Monaco", "FRA", "FRA1", ["50023"], ["AS Monaco", "AS Monaco FC", "Monaco"], {}),
    ("Montpellier", "FRA", "FRA1", ["50128"], ["Montpellier", "Montpellier HSC"], {}),
    ("Málaga", "ESP", "ESP1", ["74069"], ["Málaga", "Málaga CF"], {}),
    ("Borussia Mönchengladbach", "GER", "GER1", ["52757"],
     ["Borussia Mönchengladbach", "Borussia M'gladbach", "Mönchengladbach"], {}),
    ("Napoli", "ITA", "ITA1", ["50136"], ["Napoli", "SSC Napoli"], {}),
    ("Newcastle United", "ENG", "ENG1", ["59324"], ["Newcastle United", "Newcastle United FC", "Newcastle"], {}),
    ("Nordsjælland", "DEN", None, ["79940"], ["Nordsjælland"], {}),
    ("Olympiacos", "GRE", None, ["2610"], ["Olympiacos"], {}),
    ("Oțelul Galați", "ROU", None, ["50151"], ["Oțelul Galați", "Oţelul"], {}),
    ("PSV Eindhoven", "NED", "NED1", ["50062"], ["PSV Eindhoven", "PSV"], {}),
    ("Pafos", "CYP", None, ["2609532"], ["Pafos", "Pafos FC"], {}),
    ("Paris Saint-Germain", "FRA", "FRA1", ["52747"], ["Paris Saint-Germain", "Paris Saint-Germain FC", "PSG"],
     {"uefa": ["Paris"]}),
    ("FC Porto", "POR", "POR1", ["50064"], ["FC Porto", "Porto"], {}),
    ("Qarabağ", "AZE", "AZE1", ["60609"], ["Qarabağ", "Qarabağ FK", "Qarabag"], {}),
    ("Rangers", "SCO", "SCO1", ["50121"], ["Rangers"], {}),
    ("Real Betis", "ESP", "ESP1", ["52265"], ["Real Betis", "Real Betis Balompié"], {}),
    ("Real Madrid", "ESP", "ESP1", ["50051"], ["Real Madrid", "Real Madrid CF", "Real Madrid C.F."], {}),
    ("Real Sociedad", "ESP", "ESP1", ["50123"], ["Real Sociedad", "Real Sociedad de Fútbol"], {}),
    ("Stade Rennais", "FRA", "FRA1", ["55031"], ["Stade Rennais", "Stade Rennais FC 1901", "Rennes"], {}),
    ("AS Roma", "ITA", "ITA1", ["50137"], ["AS Roma", "Roma"], {}),
    ("Rostov", "RUS", None, ["64500"], ["Rostov"], {}),
    ("Slovan Bratislava", "SVK", "SVK1", ["52797"], ["Slovan Bratislava", "S. Bratislava"], {}),
    ("Sabah", "AZE", "AZE1", ["2609356"], ["Sabah", "Sabah FK"], {}),
    ("RB Salzburg", "AUT", "AUT1", ["50030"], ["RB Salzburg", "Salzburg"], {}),
    ("Schalke 04", "GER", "GER1", ["57388"], ["Schalke 04", "FC Schalke 04", "Schalke"], {}),
    ("Sevilla", "ESP", "ESP1", ["52714"], ["Sevilla", "Sevilla FC"], {}),
    ("Shakhtar Donetsk", "UKR", "UKR1", ["52707"], ["Shakhtar Donetsk", "Shakhtar"], {}),
    ("Sheriff Tiraspol", "MDA", None, ["69606"], ["Sheriff Tiraspol", "Sheriff"], {}),
    ("Slavia Praha", "CZE", "CZE1", ["52498"], ["Slavia Praha", "SK Slavia Praha"], {}),
    ("Sparta Praha", "CZE", "CZE1", ["50033"], ["Sparta Praha", "AC Sparta Praha"], {}),
    ("Spartak Moskva", "RUS", None, ["50068"], ["Spartak Moskva"], {}),
    ("Sporting CP", "POR", "POR1", ["50149"], ["Sporting CP", "Sporting Clube de Portugal"],
     {"uefa": ["Sporting"], "openfootball@UCL": ["Sporting"]}),
    ("FCSB", "ROU", None, ["2614166"], ["FCSB", "Steaua București"], {}),
    ("Sturm Graz", "AUT", "AUT1", ["50111"], ["Sturm Graz"], {}),
    ("VfB Stuttgart", "GER", "GER1", ["50107"], ["VfB Stuttgart", "Stuttgart"], {}),
    ("Tottenham Hotspur", "ENG", "ENG1", ["1652"], ["Tottenham Hotspur", "Tottenham Hotspur FC", "Tottenham"], {}),
    ("Trabzonspor", "TUR", "TUR1", ["52731"], ["Trabzonspor"], {}),
    ("Union Berlin", "GER", "GER1", ["77977"], ["Union Berlin", "1. FC Union Berlin"], {}),
    ("Union Saint-Gilloise", "BEL", "BEL1", ["64125"], ["Union Saint-Gilloise", "Union SG"], {}),
    ("Valencia", "ESP", "ESP1", ["52268"], ["Valencia", "Valencia CF"], {}),
    ("Viking", "NOR", "NOR1", ["52319"], ["Viking", "Viking FK"], {}),
    ("Viktoria Plzeň", "CZE", "CZE1", ["64388"], ["Viktoria Plzeň"], {}),
    ("Villarreal", "ESP", "ESP1", ["70691"], ["Villarreal", "Villarreal CF"], {}),
    ("VfL Wolfsburg", "GER", "GER1", ["64332"], ["VfL Wolfsburg", "Wolfsburg"], {}),
    ("Young Boys", "SUI", None, ["50031"], ["Young Boys"], {}),
    ("Zenit St. Petersburg", "RUS", None, ["52826"], ["Zenit St. Petersburg", "Zenit"], {}),
]

# Inhemska varianter (gäller endast inom ligans kontext). Ett lag per rad: [kanoniskt, alias...]
DOMESTIC_VARIANTS: dict[str, list[list[str]]] = {
    "ENG1": [["AFC Bournemouth", "Bournemouth"], ["Brentford", "Brentford FC"],
             ["Brighton & Hove Albion", "Brighton & Hove Albion FC"], ["Burnley", "Burnley FC"],
             ["Crystal Palace", "Crystal Palace FC"], ["Everton", "Everton FC"], ["Fulham", "Fulham FC"],
             ["Leeds United", "Leeds United FC"], ["Nottingham Forest", "Nottingham Forest FC"],
             ["Sunderland", "Sunderland AFC"], ["West Ham United", "West Ham United FC"],
             ["Wolverhampton Wanderers", "Wolverhampton Wanderers FC"]],
    "GER1": [["1. FC Heidenheim 1846", "Heidenheim"], ["FC St. Pauli 1910", "St. Pauli"],
             ["SV Werder Bremen", "Werder Bremen"]],
    "ITA1": [["ACF Fiorentina", "Fiorentina"], ["Cagliari Calcio", "Cagliari"], ["US Cremonese", "Cremonese"],
             ["Genoa CFC", "Genoa"], ["Hellas Verona FC", "Hellas Verona"], ["US Lecce", "Lecce"],
             ["Parma Calcio 1913", "Parma"], ["US Sassuolo Calcio", "Sassuolo"], ["Torino FC", "Torino"],
             ["Udinese Calcio", "Udinese"]],
    "ESP1": [["RC Celta de Vigo", "RC Celta"], ["RCD Espanyol de Barcelona", "RCD Espanyol"],
             ["Rayo Vallecano de Madrid", "Rayo Vallecano"]],
    "FRA1": [["AJ Auxerre", "Auxerre"], ["ESTAC Troyes", "ES Troyes AC"], ["Le Havre AC", "Le Havre"],
             ["RC Strasbourg Alsace", "RC Strasbourg"]],
    "NED1": [["AZ Alkmaar", "AZ"], ["FC Twente", "FC Twente '65"], ["NEC Nijmegen", "NEC"],
             ["Vitesse", "SBV Vitesse"], ["SC Cambuur-Leeuwarden", "SC Cambuur"], ["SC Heerenveen"],
             ["Willem II Tilburg", "Willem II"]],
    "POR1": [["Boavista FC", "Boavista"], ["GD Estoril Praia", "GD Estoril"], ["Gil Vicente FC", "Gil Vicente"]],
    "AZE1": [["Sumgayıt FK", "Sumgayit FK"]],
}

# openfootball-ligakoder i den tidigare arbetsboken -> tävlingskod, tidszon för lokala avsparkstider
WORKBOOK_LEAGUES: dict[str, tuple[str, str]] = {
    "ENG": ("ENG1", "Europe/London"),
    "ESP": ("ESP1", "Europe/Madrid"),
    "ITA": ("ITA1", "Europe/Rome"),
    "GER": ("GER1", "Europe/Berlin"),
    "FRANCE": ("FRA1", "Europe/Paris"),
    "NETHERLANDS": ("NED1", "Europe/Amsterdam"),
    "PORTUGAL": ("POR1", "Europe/Lisbon"),
    "TURKEY": ("TUR1", "Europe/Istanbul"),
    "BEL": ("BEL1", "Europe/Brussels"),
    "CZECH-REPUBLIC": ("CZE1", "Europe/Prague"),
    "NOR": ("NOR1", "Europe/Oslo"),
    "AZERBAIJAN": ("AZE1", "Asia/Baku"),
}


def seed_aliases(repo, now_iso: str) -> int:
    """Skapa kanoniska lag och exakta alias. Idempotent."""
    from .entities import deterministic_color, normalize_name

    db = repo.db
    created = 0
    with db.tx() as c:
        for canonical, country, dom, uefa_ids, aliases, src_aliases in CL_TEAMS:
            tid = None
            for uid in uefa_ids:
                r = c.execute("SELECT team_id FROM team_source_ids WHERE source_id='uefa' AND source_team_id=?",
                              (uid,)).fetchone()
                if r:
                    tid = r[0]
            if tid is None:
                r = c.execute("SELECT team_id FROM team_aliases WHERE alias_norm=? AND context='' AND source_id=''",
                              (normalize_name(canonical),)).fetchone()
                tid = r[0] if r else None
            if tid is None:
                a, b = deterministic_color(canonical)
                tid = c.execute("""INSERT INTO teams (name, country, domestic_competition_code, color_primary,
                    color_secondary, needs_review, created_by_source, created_at_utc) VALUES (?,?,?,?,?,0,'seed',?)""",
                                (canonical, country, dom, a, b, now_iso)).lastrowid
                created += 1
            for uid in uefa_ids:
                c.execute("INSERT OR IGNORE INTO team_source_ids (team_id, source_id, source_team_id, name_original) "
                          "VALUES (?,?,?,?)", (tid, "uefa", uid, canonical))
            for al in aliases:
                c.execute("""INSERT OR IGNORE INTO team_aliases (team_id, alias, alias_norm, context, source_id, origin,
                    created_at_utc) VALUES (?,?,?,?,?,?,?)""", (tid, al, normalize_name(al), "", "", "seed", now_iso))
            for key, als in src_aliases.items():
                sid, _, ctx = key.partition("@")  # "källa" eller "källa@kontext"
                for al in als:
                    c.execute("""INSERT OR IGNORE INTO team_aliases (team_id, alias, alias_norm, context, source_id,
                        origin, created_at_utc) VALUES (?,?,?,?,?,?,?)""",
                              (tid, al, normalize_name(al), ctx, sid, "seed", now_iso))
        for comp, groups in DOMESTIC_VARIANTS.items():
            for group in groups:
                canonical = group[0]
                r = c.execute("SELECT team_id FROM team_aliases WHERE alias_norm=? AND context=?",
                              (normalize_name(canonical), comp)).fetchone()
                if r:
                    tid = r[0]
                else:
                    a, b = deterministic_color(canonical)
                    tid = c.execute("""INSERT INTO teams (name, country, domestic_competition_code, color_primary,
                        color_secondary, needs_review, created_by_source, created_at_utc)
                        VALUES (?,?,?,?,?,0,'seed',?)""", (canonical, None, comp, a, b, now_iso)).lastrowid
                    created += 1
                for al in group:
                    c.execute("""INSERT OR IGNORE INTO team_aliases (team_id, alias, alias_norm, context, source_id,
                        origin, created_at_utc) VALUES (?,?,?,?,?,?,?)""",
                              (tid, al, normalize_name(al), comp, "", "seed", now_iso))
    return created
