"""People and places PoliDesk can illustrate with a freely licensed Wikimedia Commons photo.

Used only when no outlet photo exists for a story (see images.add_file_photos).
Each file was checked by hand on 2026-11-14 (right person or place, sensible crop,
free licence). Matching is on the headline only, and names that are ambiguous
("Ford", "Chow", "Smith", "Khamenei") need a fuller form or the right beat.

(key, kind, headline pattern, beats where the short form is allowed, Commons file)
kind "person" wins over "place"; among people, the one named first in the headline wins.
"""
import re

PEOPLE = [
    # United States
    ("trump", r"\btrump\b", None, "Official Presidential Portrait of President Donald J. Trump (2025) (3x4).jpg"),
    ("vance", r"\bvance\b", None, "March 2026 Official Vice Presidential Portrait of JD Vance.jpg"),
    ("rubio", r"\brubio\b", None, "Official portrait of Secretary Marco Rubio.jpg"),
    ("hegseth", r"\bhegseth\b", None, "Pete Hegseth Official Portrait (cropped).jpg"),
    ("schumer", r"\bschumer\b", None, "Chuck Schumer official photo.jpg"),
    ("vanhollen", r"\bvan hollen\b", None, "Chris Van Hollen official portrait 115th Congress.jpg"),
    ("jeffries", r"\bjeffries\b", None, "Rep-Hakeem-Jeffries-Official-Portrait (cropped).jpg"),
    ("mikejohnson", r"\b(mike johnson|speaker johnson)\b", None, "Speaker Mike Johnson Official Portrait (cropped)(b).jpg"),
    ("witkoff", r"\bwitkoff\b", None, "A swearing-in ceremony for Senior Adviser and Special Envoy Steve Witkoff, May 6, 2025 (cropped).jpg"),
    ("bessent", r"\bbessent\b", None, "Official portrait of Treasury Secretary Scott Bessent.jpg"),
    ("lutnick", r"\blutnick\b", None, "Howard Lutnick 2025.jpg"),
    ("noem", r"\bnoem\b", None, "Official Portrait of Secretary Kristi Noem.jpg"),
    ("newsom", r"\bnewsom\b", None, "Gavin Newsom official photo.jpg"),
    ("mamdani", r"\bmamdani\b", None, "Zohran Mamdani 05.25.25 (b).jpg"),
    ("musk", r"\b(elon )?musk\b", None, "Elon Musk (54816836217) (cropped 2) (b).jpg"),
    ("huang", r"\b(jensen huang|nvidia['’]?s huang)\b", None, "Jensen Huang Stanford 2026-04-30 010 (cropped).jpg"),
    # World
    ("putin", r"\bputin\b", None, "Vladimir Putin 2 September 2026.jpg"),
    ("zelensky", r"\bzelensk(y|yy|iy)\b", None, "Volodymyr Zelensky Official portrait.jpg"),
    ("netanyahu", r"\bnetanyahu\b", None, "Benjamin Netanyahu, February 2023.jpg"),
    ("burnham", r"\bburnham\b", None, "Prime Minister Andy Burnham portrait (cropped).jpg"),
    ("starmer", r"\bstarmer\b", None, "Prime Minister Keir Starmer Portrait (cropped).jpg"),
    ("badenoch", r"\bbadenoch\b", None, "Official portrait of Kemi Badenoch MP crop 2, 2024.jpg"),
    ("macron", r"\bmacron\b", None, "Emmanuel Macron 2025 (cropped).jpg"),
    ("lecornu", r"\blecornu\b", None, "Sébastien Lecornu 2024 (2x3 crop).jpg"),
    ("merz", r"\bmerz\b", None, "2024-08-21 Friedrich Merz in Erfurt 2024 STP 3041 by Stepro (3x4 cropped).jpg"),
    ("xi", r"\bxi( jinping)?\b", None, "Xi Jinping on August 18, 2026 (cropped).jpg"),
    ("modi", r"\bmodi\b", None, "Official Photograph of Prime Minister Narendra Modi Portrait.png"),
    ("erdogan", r"\berdo(g|ğ)an\b", None, "10.11.2026 - Reunião Bilateral com o Presidente da Turquia - 55645239849 (Recep Tayyip Erdoğan).jpg"),
    ("mojtaba", r"\bmojtaba\b", None, "Portrait of Mojtaba Khamenei.jpg"),
    ("alikhamenei", r"\bali khamenei\b", None, "Ali Khamenei Nowruz message official portrait 1397 02.jpg"),
    ("pezeshkian", r"\bpezeshkian\b", None, "Masoud Pezeshkian Moscow 2026.jpg"),
    ("meloni", r"\bmeloni\b", None, "Giorgia Meloni Official 2024 (cropped).jpg"),
    ("vonderleyen", r"\bvon der leyen\b", None, "Ursula von der Leyen 2024.jpg"),
    ("guterres", r"\bguterres\b", None, "António Guterres United Nations Secretary-General in 2024 (cropped).jpg"),
    ("rutte", r"\brutte\b", None, "Mark Rutte, 23.03.23 (cropped).jpg"),
    ("kimjongun", r"\bkim jong[ -]?un\b", None, "Kim Jong-un and Vladimir Putin (2023-09-13) 12 (cropped).jpg"),
    ("milei", r"\bmilei\b", None, "Javier Milei en el Salón Blanco 2 (cropped).jpg"),
    ("lula", r"\blula\b", None, "Foto oficial de Luiz Inácio Lula da Silva (estreita).jpg"),
    ("sheinbaum", r"\bsheinbaum\b", None, "Claudia Sheinbaum Argentina v Spain 19 July 2026-283.jpg"),
    ("mbs", r"\b(mohammed bin salman|bin salman|mbs)\b", None, "الصورة الرسمية للأمير محمد بن سلمان بن عبدالعزيز آل سعود (مقصوصة).jpg"),
    ("delcy", r"\bdelcy\b", None, "Delcy Rodríguez - 02 (19-01-2026) (cropped 2).jpg"),
    ("sharaa", r"\b(al-)?sharaa\b", None, "Ahmed al-Sharaa, President of Syria, in March 2026.jpg"),
    ("diazcanel", r"\bd(i|í)az-canel\b", None, "Miguel Díaz-Canel 2025.jpg"),
    ("tamim", r"\b(emir of qatar|tamim)\b", None, "Tamim bin Hamad Al Thani Moscow 2026.jpg"),
    ("takaichi", r"\btakaichi\b", None, "Official portrait of Sanae Takaichi, Prime Minister of Japan (HD).jpg"),
    # Canada
    ("carney", r"\bcarney\b", None, "Mark Carney Argentina v Spain 19 July 2026-303 (3x4 close up cropped).jpg"),
    ("poilievre", r"\bpoilievre\b", None, "Pierre Poilievre in 2023 (edited).jpg"),
    ("avilewis", r"\bavi lewis\b", None, "Avi Lewis September 2025 Ottawa.jpg"),
    ("blanchet", r"\bblanchet\b", None, "Yves-François Blanchet Entrevue no smile 2023 (cropped).png"),
    ("champagne", r"\b(fran(c|ç)ois-philippe champagne)\b", (r"\bchampagne\b", {"federal"}), "François-Philippe Champagne - 2017 (32684778620) (cropped).jpg"),
    ("joly", r"\bjoly\b", None, "Mélanie Joly - UNGA 2023 (53203204441) (cropped).jpg"),
    ("anand", r"\banita anand\b", (r"\banand\b", {"federal"}), "Anita Anand, December 2025 (P-068488 00-05) (cropped).jpg"),
    ("dougford", r"\b(doug ford|premier ford|ford government|ford gov['’]?t)\b", (r"\bford(['’]s)?\b", {"ontario"}), "Doug Ford in Toronto June 2025 (edited).jpg"),
    ("stiles", r"\bmarit stiles\b", (r"\bstiles\b", {"ontario"}), "Marit Stiles, Windsor, Ontario, 2026-11-11 05.jpg"),
    ("crombie", r"\bcrombie\b", None, "Bonnie Crombie at 2017 AMO Conference (36541302906) (cropped3).jpg"),
    ("chow", r"\b(olivia chow|mayor chow)\b", (r"\bchow\b", {"toronto"}), "REUNIÓN CON LA ALCALDESA DE TORONTO, OLIVIA CHOW, 04 DE MARZO DE 2024 (cropped).jpg"),
    ("dsmith", r"\b(danielle smith|premier smith)\b", None, "Pete Hoekstra with Danielle Smith June 2025 (cropped(a)).jpg"),
    ("eby", r"\b(david eby|premier eby)\b", None, "David Eby - 2022 (52507022370) (cropped).png"),
    ("kinew", r"\bkinew\b", None, "Wab Kinew in Sept 2024 (cropped).jpg"),
    ("moe", r"\b(scott moe|premier moe)\b", None, "Scott Moe at US EPA (cropped).jpg"),
    ("frechette", r"\bfr(e|é)chette\b", None, "Christine Fréchette 2024.jpg"),
]

# Government buildings and neutral landmarks. No places for active war zones:
# a scenic photo would be the wrong note for those stories.
PLACES = [
    ("whitehouse", r"\bwhite house\b", None, "WhiteHouseSouthFacade.JPG"),
    ("pentagon", r"\bpentagon\b", None, "The Pentagon January 2008.jpg"),
    ("maralago", r"\bmar-a-lago\b", None, "Mar-a-Lago, Palm Beach. FL, US.jpg"),
    ("scotus", r"\b(us|u\.s\.) supreme court\b", (r"\bsupreme court\b", {"us"}), "USSupremeCourtWestFacade.JPG"),
    ("capitol", r"\b(capitol hill|us congress|u\.s\. congress)\b", (r"\b(congress|senate|house (republicans|democrats|speaker)|shutdown|capitol)\b", {"us"}), "United States Capitol west front edit2.jpg"),
    ("scc", r"\bsupreme court of canada\b", (r"\bsupreme court\b", {"federal", "ontario", "toronto"}), "Supreme Court of Canada, Wellington Street, Ottawa.jpg"),
    ("rideau", r"\b(rideau hall|governor general)\b", None, "Rideau Hall04.jpg"),
    ("parliamenthill", r"\bparliament hill\b", (r"\b(ottawa|house of commons|parliament|commons|mps?)\b", {"federal"}), "Parliament-Ottawa.jpg"),
    ("queenspark", r"\bqueen['’]?s park\b", (r"\b(legislature|mpps?)\b", {"ontario"}), "Queen's Park - Toronto - 2010 (cropped-rotated).jpg"),
    ("torontocityhall", r"\btoronto city hall\b", (r"\b(city hall|council|councillors?)\b", {"toronto"}), "City Hall, Toronto, Ontario.jpg"),
    ("albertaleg", r"\balberta\b", None, "Alberta Legislature Building, June 7, 2024.jpg"),
    ("quebecleg", r"\bqu(e|é)bec\b", None, "Québec - Hôtel du Parlement 3.jpg"),
    ("manitobaleg", r"\bmanitoba\b", None, "Parliamentwinnipeg manitoba.jpg"),
    ("saskleg", r"\bsaskatchewan\b", None, "Saskatchewan Legislative Building - Regina.jpg"),
    ("kremlin", r"\b(kremlin|moscow)\b", None, "Moscow 05-2012 Kremlin 22.jpg"),
    ("downing", r"\bdowning street\b", None, "10 Downing Street. MOD 45155532 (cropped).jpg"),
    ("westminster", r"\b(westminster|uk parliament|british parliament)\b", None, "Houses of Parliament in 2022 (cropped).jpg"),
    ("reichstag", r"\b(bundestag|reichstag)\b", None, "Reichstagsgebäude von Westen.jpg"),
    ("berlaymont", r"\b(european commission|eu commission|brussels)\b", None, "Belgique - Bruxelles - Schuman - Berlaymont - 01.jpg"),
    ("un", r"\b(united nations|un general assembly|un security council)\b", None, "2024-11-18-Headquarters of the United Nations-0605.jpg"),
    ("greathall", r"\bbeijing\b", None, "China Senate House.jpg"),
    ("diet", r"\btokyo\b", None, "National Diet Building 02.jpg"),
    ("mexpalace", r"\bmexico city\b", None, "Palacio Nacional, México D.F., México, 2013-10-16, DD 119.JPG"),
    ("ankara", r"\b(ankara|t(u|ü)rkiye|turkey)\b", None, "Presidential Palace Main.jpg"),
    ("doha", r"\b(doha|qatar)\b", None, "Doha skyline in the morning (12544910974).jpg"),
    ("riyadh", r"\briyadh\b", None, "Riyadh Skyline.jpg"),
    ("havana", r"\bhavana\b", None, "Cuba libre (6941395159).jpg"),
    ("caracas", r"\bcaracas\b", None, "Caracas desde el ávila.jpg"),
]

# When nothing in the headline matches, local beats still get their own building.
BEAT_DEFAULT = {"federal": "parliamenthill", "ontario": "queenspark", "toronto": "torontocityhall"}

FILES = {key: f for key, _, _, f in PEOPLE + PLACES}
_RULES = [(key, "person", re.compile(p, re.I), (re.compile(s[0], re.I), s[1]) if s else None) for key, p, s, _ in PEOPLE] + \
         [(key, "place", re.compile(p, re.I), (re.compile(s[0], re.I), s[1]) if s else None) for key, p, s, _ in PLACES]


def match(title, topic):
    """The best entity key for a headline, or None. People first (earliest in the headline), then places, then the beat."""
    hits = []
    for key, kind, rx, short in _RULES:
        m = rx.search(title)
        if not m and short and topic in short[1]:
            m = short[0].search(title)
        if m:
            hits.append((0 if kind == "person" else 1, m.start(), key))
    if hits:
        return min(hits)[2]
    return BEAT_DEFAULT.get(topic)
