UNPROTECTED_ROLES = [
    253581140072464384,
    253583191732912129,
    577598290607079445,
    253583702162931723,
    253583831557341184,
    357592666340458497,
    357592486455017473,
    585265871941926913,
    412954620961226763,
    279746737596399617,
    576127374190575626,
    279039481875529729,
    332255196799434753,
    467123881291808799,
    307419780065787905,
]

UNLOGGED_CHANNELS = [359935078983270410]

R6_STATUS_URL = "https://game-status-api.ubisoft.com/v1/instances?appIds=e3d5ea9e-50bd-43b7-88bf-39794f4e3d40,fb4cc4c9-2063-461d-a1e8-84a7d36525fc,4008612d-3baf-49e4-957a-33066726a7bc"

R6_STATUS_APPIDS = {
    "PC": "e3d5ea9e-50bd-43b7-88bf-39794f4e3d40",
    "XBOXONE": "4008612d-3baf-49e4-957a-33066726a7bc",
    "PS4": "fb4cc4c9-2063-461d-a1e8-84a7d36525fc",
}

R6_STATUS_EMOTES = {
    "maintenance": 505829600262357002,
    "degraded": 505815964575596545,
    "online": 505815964798156815,
    "interrupted": 505815964739305512,
}

R6_STATUS_COLORS = {
    "maintenance": 0x000000,
    "degraded": 0xFBC900,
    "online": 0x95C11F,
    "interrupted": 0xF80303,
}

VALID_REGIONS = ["NA", "NA-W", "NA-E", "NA-C", "EU", "SEAS", "RU", "ANZ", "BR", "ZA"]

VALID_PLATFORMS = ["PC", "Xbox", "PSN"]

VALID_RANKS = [
    "Copper",
    "Bronze",
    "Silver",
    "Gold",
    "Plat",
    "Platinum",
    "Diamond",
    "Champ",
    "Champion",
]

VALID_OTHER_PRESET = ["Chill", "Serious", "Mic-Req", "Renown-Boost", "THunt"]

VALID_CHANNEL_STRINGS = VALID_REGIONS + VALID_PLATFORMS + VALID_RANKS

SUDO_ROLES = [
    253582130460753921,
    253581597641670657,
    269511788192595969,
    278967111454556170,
    278980438754590731,
    286363905544945664,
]

REGEX = {
    "drama_base": r"(?<![\w])({})s?(?![\w])",
    "drama": "",
    "uplay": r"(?<![\w])(uplay|u play)(?![\w])",
    "dox": r"(?<![\w])(?![\w])[!#$%&'*+./0-9=?_`a-z{|}~^-]+@[.a-z-]+\.(?:com|org|net)",
}

REGEX["drama"] = REGEX["drama_base"].format("")

ROLES = {
    "muted": 279039481875529729,
    "staff": 278967111454556170,
    "pc": 253583191732912129,
    "ateveryone": 253581140072464384,
    "ps4": 253583831557341184,
    "xbox": 253583702162931723,
    "r6news": 357592666340458497,
    "bots": 278980438754590731,
    "banteams": 351548451718430721,
    "seriousd": 279746737596399617,
    "vcmuted": 332255104822673408,
    "invitationals": 412954620961226763,
    "tagmaster": 467123881291808799,
    "servernews": 357592486455017473,
    "esportsnews": 577598290607079445,
}


REACTS = {
    "delete": 531631667383762954,
    "mute": 531631911966081035,
    "24mute": 531631775122718720,
    "48mute": 531631830449782785,
    "check": 531632046980988943,
    "no": 426768929172488194,
    "ban": 531631981524418560,
    "pc": 430480519323582464,
    "ps4": 430480566492594176,
    "xbox": 430480610025537546,
    "invitationals": 347822883122446336,
    "r6ping": 430480112262316052,
    "esportsping": 585337568523059211,
    "rules": 530880811231215636,
    "serverping": 430480423039008778,
}


CHANS = {
    "staff": 276407407117074432,
    "modmail": 279356892193751041,
    "mm_category": 450707412966703120,
    "drama": 466756995517775872,
    "star": 332258548635664385,
    "actions": 279327718368083968,
    "rules": 286359381841412098,
    "watch": 314827694200061953,
    "serverlog": 269545820326461441,
    "muted": 286369301600927747,
    "vclog": 279522178515337216,
    "twitch": 271403816497184768,
    "tweets": 590705874402541568,
    "roleswap": 357581480110850049,
    "servernews": 280884809486827520,
    "gamenews": 270315303257243649,
    "esportsnews": 320053131545149441,
    "rolereminder": 358275617495580673,
    "servermetrics": 460214338003795989,
    "registration": 278959675888893952,
    "twitchinvupdates": 412426123587354625,
    "scrimspc": 290274342904922112,
    "scrimsps4": 380632834437808129,
    "scrimsxbox": 380633112394072064,
    "plftpc": 290428408465195008,
    "plftps4": 290428617773678592,
    "plftxbox": 290428645883772928,
    "tlfppc": 290428366312701962,
    "tlfpps4": 290428522080763904,
    "tlfpxbox": 290428554968301569,
    "lfgnapc": 269519917693272074,
    "lfgnaps4": 282076089927598081,
    "lfgnaxbox": 282076117651947520,
    "lfgeupc": 269566972977610753,
    "lfgeups4": 282076300838043648,
    "lfgeuxbox": 282076329829072897,
    "lfganzpc": 282076880285204480,
    "lfganzps4": 282076800698548224,
    "lfganzxbox": 282076856201510914,
    "lfgseaspc": 269567077805719552,
    "lfgseasps4": 282076615784136705,
    "lfgseasxbox": 282076628153139200,
    "ubireports": 360541244570468353,
    "registration": 278959675888893952,
    "registration": 278959675888893952,
    "registration": 278959675888893952,
    "registration": 278959675888893952,
    "genbotspam": 278986547187941377,
}

CATS = {
    "mmnew": 590694194004230145,
    "mmreply": 590694194004230145,
    "mmwfr": 590709606007701545,
    "mmread": 590709606007701545,
    "mmgraveyard": 590724454309429278,
}

SERVERS = {"main": 253581140072464384, "ban": 350379919806824449}

CAT_TRANSITION_ORDER = [590694194004230145, 590709606007701545, 590724454309429278]

CAT_TRANSITION = {
    590694194004230145: 590709606007701545,  # new / reply to wfr / closed
    590709606007701545: 590724454309429278,  # wfr / closed to graveyard
    590724454309429278: "delete",  # graveyard to deletion
}

PLAYER_LF_TEAM_CHANS = [CHANS["plftpc"], CHANS["plftps4"], CHANS["plftxbox"]]

TEAM_LF_PLAYER_CHANS = [CHANS["tlfppc"], CHANS["tlfpps4"], CHANS["tlfpxbox"]]

TEAM_CHANS = PLAYER_LF_TEAM_CHANS + TEAM_LF_PLAYER_CHANS

SCRIM_CHANS = [CHANS["scrimspc"], CHANS["scrimsps4"], CHANS["scrimsxbox"]]

LFG_CHANS = [
    CHANS["lfgnapc"],
    CHANS["lfgnaps4"],
    CHANS["lfgnaxbox"],
    CHANS["lfgeupc"],
    CHANS["lfgeups4"],
    CHANS["lfgeuxbox"],
    CHANS["lfganzpc"],
    CHANS["lfganzps4"],
    CHANS["lfganzxbox"],
    CHANS["lfgseaspc"],
    CHANS["lfgseasps4"],
    CHANS["lfgseasxbox"],
]

DISCORD_EPOCH = 1420070400000

MODMAIL_SYMBOLS = {"new": "▲", "wfr": "○", "reply": "●", "read": "✓"}

MSGS = {
    "action": "```\nAction: {action}\nUser(s):{username}#{discrim} ({id})\nReason: {reason}```{optional_content}",
    "msg_content_error": "I've deleted your message in {} since I have detected your message might not meet the channels guidelines! Please review the guidelines in the pins and if you feel your post should be allowed, feel free to use me to modmail to staff!",
    "banmsg": "You have been banned from the Rainbow6 discord. If you wish to appeal this ban, please fill out this form:\n<https://goo.gl/forms/kSVm0dfdO075PAOB2>",
    "dramaerror": "Can't {} {} because they're not on the server.{}",
    "modmailaction": "→ I sent a message to {username} ({id}) {reason}, please refer to <#{action_log_id}> for more info",
    "modmailfirstime": "→ I sent a message to {username} ({id})  to remind them to read the welcome DM as they attempted to DM me without any roles",
    "warn": "**You have been warned on {server}** {reason}",
    "lfg_awareness": "We've recently revamped the LFG and Voice Channel experience on this Discord, be sure to check out the pins of this channel to see how to set the title of your voice channel and/or limit the number of people who can join it!",
}

ROLE_ALIASES = {
    "computer": 253583191732912129,
    "xboxone": 253583702162931723,
    "xbox one": 253583702162931723,
    "play station": 253583831557341184,
    "playstation": 253583831557341184,
    "ps4": 253583831557341184,
    "x1": 253583702162931723,
    "xb1": 253583702162931723,
}

MUTED_MESSAGES = {
    "timed": "You have been muted from communicating on this discord server for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. The channel <#{muted}> is for you to communicate with staff to clarify what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. We have the channel as a courtesy to our users, as we use the channel instead of outright banning people. Spamming in the muted chat or being rude to staff will have you permanently banned.When your mutes time runs out, the role will be automatically removed and you'll have to return to <#{rules}> where you can once again pick up a new platform role and rejoin the discussions. If you have any questions, you can mention a discord staff member, but do so in a respectful manner and remember to follow the rules in the future. ",
    "timed_over": "Your mute has ended but in order to regain access to the server you'd need to visit the <#{roles}> to reassign yourself a platform role. Also, please take the time to review the <#{rules}> channel to help prevent any further infractions.",
    "plain": "You have been muted from communicating on this discord server. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. The channel <#{muted}> is for you to communicate with staff to clarify what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. We have the channel as a courtesy to our users, as we use the channel instead of outright banning people. Spamming in the muted chat or being rude to staff will have you permanently banned. If you have any questions, you can mention a discord staff member, but do so in a respectful manner and remember to follow the rules in the future.",
}

CBAN_MESSAGES = {
    "timed": "You have been temporarily banned from the {cban_name} channel(s) for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}> or within the rules of the channel(s). Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. When your mutes time runs out, the role will be automatically removed and you'll be able to rejoin the discussions. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future.",
    "plain": "You have been banned from the {cban_name} channel(s). This has occurred due to you breaking one or more of the rules outlined in <#{rules}> or within the rules of the channel(s). Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future.",
}
