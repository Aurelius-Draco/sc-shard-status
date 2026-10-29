"""Who made the app, the ground rules it keeps, and its sister app. Shown on the About tab and in the README."""

AUTHOR = {
    "name": "Aurelius_Draco",
    "repo": "https://github.com/Aurelius-Draco/sc-shard-status",
    "picture": "aurelius-draco.jpg",   # in scstatus/static/img
}

LINKS = [
    {"icon": "citizen", "title": "Citizen page", "text": "Aurelius_Draco on RSI",
     "url": "https://robertsspaceindustries.com/en/citizens/Aurelius_Draco",
     "about": "Add me as a friend or send me a message in game."},
    {"icon": "gift", "title": "New to Star Citizen?", "text": "Referral code STAR-VD9W-346V",
     "url": "https://www.robertsspaceindustries.com/enlist?referral=STAR-VD9W-346V",
     "about": "Sign up with it and you start with 50,000 UEC."},
]

# Cross-links between the apps (shown on About and in the README)
ALSO_BY = [
    {"name": "SC Inventory Tracker", "url": "https://github.com/Aurelius-Draco/sc-inventory-tracker",
     "about": "Keeps track of what you've stored at every station: scans the storage kiosk, follows Game.log, "
              "wish lists with where to buy or craft, and ship fittings."},
]

MESSAGE = [
    "I built this after losing an evening (and a pile of items) to a contract that was never going to complete. "
    "It reads what the game already tells you and puts it in plain English. It's free and always will be.",
    "The only thing I ask in return: if you see me in game or in chat, say hi, and if you're running team "
    "gameplay, invite me along.",
]

RULES = [
    "It only reads your screen (the game's own debug overlay), Game.log and the game's text file. It never "
    "touches the game's memory or network traffic, and never sends mouse or keyboard input.",
    "In this version nothing leaves your PC. Anything meant for the future community service is shown to you "
    "first, with your handle, other players' names, account numbers, session ids and IP addresses removed.",
    "Issue Council reports are drafts for you to check and submit yourself.",
    "The dashboard only answers this PC (127.0.0.1).",
    "Not affiliated with or endorsed by Cloud Imperium Games. Star Citizen is a trademark of Cloud Imperium "
    "Rights LLC.",
]
