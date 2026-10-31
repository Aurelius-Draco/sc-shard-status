"""Who made the app, the ground rules it keeps, and its sister app. Shown on the About tab and in the README."""

AUTHOR = {
    "name": "Aurelius_Draco",
    "repo": "https://github.com/Aurelius-Draco/sc-shard-status",
    "picture": "aurelius-draco.jpg",   # in scstatus/static/img
}

LINKS = [
    {"icon": "citizen", "title": "Community site", "text": "verseshards.com",
     "url": "https://verseshards.com",
     "about": "Live shard board, a page for every known issue, Issue Council links to upvote and workarounds that worked."},
    {"icon": "citizen", "title": "Discord", "text": "Verse Shards server",
     "url": "https://discord.gg/8kH5pfHYbe",
     "about": "Shard alerts as they happen, help with the app, new versions, and a bot that answers /board, /issue and /sell."},
    {"icon": "citizen", "title": "Add Aurelius_Draco as a friend", "text": "Citizen page on RSI",
     "url": "https://robertsspaceindustries.com/citizens/Aurelius_Draco",
     "about": "Send a friend request, a message, or invite me along on team gameplay."},
    {"icon": "citizen", "title": "Spectrum thread", "text": "SC Shard Status on Spectrum",
     "url": "https://robertsspaceindustries.com/spectrum/community/SC/forum/50172/thread/sc-shard-status-free-app-that-scores-your-shard-s-/575329",
     "about": "Questions, ideas and what's coming next, where other players can see them."},
    {"icon": "citizen", "title": "Help wanted", "text": "verseshards.com/help",
     "url": "https://verseshards.com/help",
     "about": "Testers with 1440p, 4K or ultrawide screens, and moderators and admins for the community side."},
    {"icon": "gift", "title": "New to Star Citizen?", "text": "Referral code STAR-VD9W-346V",
     "url": "https://www.robertsspaceindustries.com/enlist?referral=STAR-VD9W-346V",
     "about": "Sign up with it and you start with 50,000 UEC."},
]

STAR = {"text": "Finding this useful? A star on GitHub helps other players find it and trust it.",
        "url": "https://github.com/Aurelius-Draco/sc-shard-status", "api": "https://api.github.com/repos/Aurelius-Draco/sc-shard-status"}

COMING = ("Coming soon: org tools. Plan org events, pick the healthiest shard and server for them from live readings, "
          "and rally your members to the right place at the right time.")

# Cross-links between the apps (shown on About and in the README)
ALSO_BY = [
    {"name": "SC Inventory Tracker", "url": "https://github.com/Aurelius-Draco/sc-inventory-tracker",
     "download": "https://github.com/Aurelius-Draco/sc-inventory-tracker/releases/latest",
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
    "Nothing leaves your PC unless you turn on sharing. The community board summary is shown to you on the Set up "
    "tab and never includes your handle, other players' names, account or session numbers, or IP address.",
    "Issue Council reports are drafts for you to check and submit yourself.",
    "The optional Mark this moment hotkey is registered with Windows, which tells the app only when that one "
    "combination is pressed. The app never watches the keyboard.",
    "Group posts and pirate reports go only when you press the button, with the area (never the exact place), and "
    "your handle only if you add it.",
    "The dashboard only answers this PC (127.0.0.1).",
    "Not affiliated with or endorsed by Cloud Imperium Games. Star Citizen is a trademark of Cloud Imperium "
    "Rights LLC.",
]
