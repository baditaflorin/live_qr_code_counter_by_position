"""Seed data — Czocha Day 1: The Opening (90 minutes in the Knights' Hall).

Each entry: (text, block, formation, position).
Formation hints which physical layout the room is in:
  - line              spectrum from one end to the other
  - spectrum          5-point line, "first option" vs "second option"
  - two_camps         binary, yes/no on the floor
  - circle            step-in if true
  - matrix_2x2        four-corners
  - privilege_walk    everyone on a line, those who answer yes step forward
"""

CZOCHA_DAY_1 = [
    # Block 1 — Arriving in the body
    ("Order yourselves by how far you travelled to be here today.",
        "Block 1 · Arriving in the Body", "line", 1),
    ("How awake do you feel right now — barely here, to fully arrived.",
        "Block 1 · Arriving in the Body", "line", 2),
    ("How nervous were you walking into this hall — calm, to deeply nervous.",
        "Block 1 · Arriving in the Body", "line", 3),
    ("How much sleep did you get this week — almost none, to plenty.",
        "Block 1 · Arriving in the Body", "line", 4),

    # Block 2 — How you move through the world
    ("I recharge alone · I recharge with people.",
        "Block 2 · How You Move Through the World", "spectrum", 1),
    ("I plan everything · I follow what unfolds.",
        "Block 2 · How You Move Through the World", "spectrum", 2),
    ("I lead easily · I prefer to support.",
        "Block 2 · How You Move Through the World", "spectrum", 3),
    ("I speak first · I listen first.",
        "Block 2 · How You Move Through the World", "spectrum", 4),
    ("I move fast through life right now · I move slowly.",
        "Block 2 · How You Move Through the World", "spectrum", 5),

    # Block 3 — What you carry
    ("I arrived this week tired · I arrived rested.",
        "Block 3 · What You Carry", "spectrum", 1),
    ("I am carrying grief I have not put down.",
        "Block 3 · What You Carry", "spectrum", 2),
    ("I am proud of who I am right now.",
        "Block 3 · What You Carry", "spectrum", 3),
    ("I love what I do for a living.",
        "Block 3 · What You Carry", "spectrum", 4),
    ("I have something this year I am quietly celebrating.",
        "Block 3 · What You Carry", "spectrum", 5),

    # Block 4 — How you trust
    ("I trust easily — most people earn it back · I trust slowly, by default.",
        "Block 4 · How You Trust", "two_camps", 1),
    ("I have been hurt by trusting the wrong person.",
        "Block 4 · How You Trust", "two_camps", 2),
    ("I am better at being trusted than at trusting.",
        "Block 4 · How You Trust", "two_camps", 3),
    ("I tell the people close to me what I really feel.",
        "Block 4 · How You Trust", "two_camps", 4),
    ("I have a friend I would call at 3am.",
        "Block 4 · How You Trust", "two_camps", 5),
    ("I would say I am, on most days, lonely.",
        "Block 4 · How You Trust", "two_camps", 6),

    # Block 5 — What you want from this week
    ("I came mostly to learn · I came mostly to be changed.",
        "Block 5 · What You Want From This Week", "line", 1),
    ("I want to be more open by Friday than I am tonight.",
        "Block 5 · What You Want From This Week", "line", 2),
    ("There is a version of me I would like to meet here.",
        "Block 5 · What You Want From This Week", "line", 3),
    ("I am open to letting strangers see me cry this week.",
        "Block 5 · What You Want From This Week", "line", 4),
    ("I am willing to say something this week I have never said aloud.",
        "Block 5 · What You Want From This Week", "line", 5),

    # Block 6 — Closing the circle
    ("Step in if you stood alone at least once tonight.",
        "Block 6 · Closing the Circle", "circle", 1),
    ("Step in if you saw yourself in someone you did not expect.",
        "Block 6 · Closing the Circle", "circle", 2),
    ("Step in if you learned something about someone here you want to know more about.",
        "Block 6 · Closing the Circle", "circle", 3),
    ("Step in if you are willing to be more open tomorrow than you were tonight.",
        "Block 6 · Closing the Circle", "circle", 4),
    ("Step in if — right now — you trust this room a little more than when you walked in.",
        "Block 6 · Closing the Circle", "circle", 5),

    # Privilege Walk · Block A — Family & Access
    ("Take two steps forward if both of your parents are still married.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 1),
    ("Take two steps forward if you grew up with a father figure in the home.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 2),
    ("Take two steps forward if you had access to a private education.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 3),
    ("Take two steps forward if you had access to a free tutor growing up.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 4),
    ("Take two steps forward if you have never had to worry about your phone being shut off.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 5),
    ("Take two steps forward if you never had to help your mother or father pay the bills.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 6),
    ("Take two steps forward if it is not because of athletic ability that you do not have to pay for university.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 7),
    ("Take two steps forward if you have never worried where your next meal would come from.",
        "Privilege Walk · Block A — Family & Access", "privilege_walk", 8),

    # Privilege Walk · Block B — Where you were born
    ("Take two steps forward if you were born in a country where your passport lets you travel to most places without needing a visa in advance.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 1),
    ("Take two steps forward if the language you spoke at home is also the language taught in your country's best universities.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 2),
    ("Take two steps forward if the hospital where you were born had a paediatric ward, clean water, and reliable electricity on the day you arrived.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 3),
    ("Take two steps forward if the street you grew up on was paved, lit at night, and safe to walk down alone after dark.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 4),
    ("Take two steps forward if you had reliable internet at home before you finished secondary school.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 5),
    ("Take two steps forward if no member of your immediate family ever had to leave the country to find work, send money home, or escape a war.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 6),
    ("Take two steps forward if when you were a child, the news from your region was reported by international outlets as context, not as crisis.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 7),
    ("Take two steps forward if you have never had to think of your country, your village, or your people as something that has to be explained to outsiders before a conversation can begin.",
        "Privilege Walk · Block B — Where You Were Born", "privilege_walk", 8),

    # Privilege Walk · Block C — Parents, Finance & Opportunity
    ("Take two steps forward if at least one of your parents finished a university degree.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 1),
    ("Take two steps forward if someone in your family could explain to you, before you applied, how university admissions actually work.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 2),
    ("Take two steps forward if a parent or close relative was able to introduce you to your first paid job, internship, or mentor.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 3),
    ("Take two steps forward if you grew up in a home with more than fifty books on the shelves.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 4),
    ("Take two steps forward if when you were eighteen, your family could have lent or given you a month's rent in an emergency without it being a crisis.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 5),
    ("Take two steps forward if you have travelled outside your home country at least once for reasons that were not work, study, or escape.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 6),
    ("Take two steps forward if you have never had to translate official letters, bills, or appointments for a parent.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 7),
    ("Take two steps forward if your parents owned the home you grew up in for most of your childhood.",
        "Privilege Walk · Block C — Parents, Finance & Opportunity", "privilege_walk", 8),

    # Privilege Walk · Block D — Entrepreneurship
    ("Take two steps forward if you have been able to work on an idea for at least six months without a salary, without going into debt.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 1),
    ("Take two steps forward if someone in your family has started, owned, or run a business, so you grew up watching how it was done.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 2),
    ("Take two steps forward if when you needed your first round of money, there was at least one person you could call who could write a cheque without changing their life.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 3),
    ("Take two steps forward if you have access to a professional network where the words 'I'm thinking of starting something' open doors instead of closing them.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 4),
    ("Take two steps forward if your venture failed tomorrow, you have a place to live and food to eat for the next twelve months without working.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 5),
    ("Take two steps forward if you have never been told that the way you speak, look, or are named makes investors, clients, or partners take you less seriously.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 6),
    ("Take two steps forward if you have a passport that lets you incorporate, bank, and travel to your customers without applying for permission.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 7),
    ("Take two steps forward if you have at least one mentor who has already done what you are trying to do, and who answers when you call.",
        "Privilege Walk · Block D — Entrepreneurship", "privilege_walk", 8),

    # Four corners — single matrix question
    ("Where do you live, in the work you do? — Builders (create, inward) · Dreamers (create, outward) · Fixers (maintain, inward) · Connectors (maintain, outward).",
        "The Four Corners — Where Do You Live", "matrix_2x2", 1),
]


def as_records() -> list[dict]:
    return [
        {"text": text, "block": block, "formation": form, "position": pos}
        for (text, block, form, pos) in CZOCHA_DAY_1
    ]
