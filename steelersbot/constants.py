UNLOGGED_CHANNELS = []

STEELERS_SLEEPER_QUERY = {"operationName":"load_topics",
                          "variables":{},
                          "query":"query load_topics {\n        topics(channel_id: \"263046764741783552\", order_by: \"last_created\"){\n          created\n          title\n          title_map\n          topic_id\n          player_tags\n          channel_tags\n          }\n\n        }"
                         }
GEN_SLEEPER_QUERY = {"operationName":"load_topics",
                     "variables":{},
                     "query":"query load_topics {\n        topics(channel_id: \"170000000000000000\", order_by: \"last_created\"){\n          created\n          title\n          title_map\n          topic_id\n          player_tags\n          channel_tags\n          }\n\n        }"
                    }

TEAMS_SLEEPER_QUERY = {"operationName":"teams",
                       "variables":{},
                       "query":"query teams {\n        teams(sport: \"nfl\"){\n          metadata\n          name\n          team\n        }\n      }"
                       }
                       
SLEEPER_TEAM_NAME_MAP = {
                        "LAC": "sd",
                        "LAR": "la",
                        "JAX": "jac"
                        }
                 
REGEX = {'drama_base': r"(?<![\w])({})s?(?![\w])",
        'drama': '',
        'uplay': r"(?<![\w])(uplay|u play)(?![\w])", 
        'dox': r"(?<![\w])(?![\w])[!#$%&'*+./0-9=?_`a-z{|}~^-]+@[.a-z-]+\.(?:com|org|net)"
        }

REGEX['drama'] = REGEX['drama_base'].format('')
       
ROLES = {
        "ateveryone" : 90646584299118592,
        "seahawks" : 585998350302707733,
        "49ers" : 585998287098740760,
        "rams" : 585998191028338690,
        "cardinals" : 585998124280184852,
        "buccaneers" : 585998077433872394,
        "saints" : 585997975453696001,
        "panthers" : 585997895619182619,
        "falcons" : 585997821329670206,
        "vikings" : 585997738374725643,
        "packers" : 585997609684959242,
        "lions" : 585997544241233920,
        "bears" : 585997429904769035,
        "redskins" : 585997344273858592,
        "eagles" : 585997230868135954,
        "giants" : 585997137985273867,
        "cowboys" : 585997114627063829,
        "jets" : 585997090153562154,
        "patriots" : 585997017449365516,
        "dolphins" : 585996944254435349,
        "bills" : 585996813195280412,
        "browns" : 585996738083422226,
        "bengals" : 585996654138621954,
        "ravens" : 585996591358279690,
        "titans" : 585996512975126528,
        "jaguars" : 585996361770598400,
        "colts" : 585996153753960450,
        "texans" : 585996107474141185,
        "raiders" : 585996026494844948,
        "chargers" : 585995802304839683,
        "chiefs" : 585995712039485475,
        "broncos" : 585995344999874580,
        "nitro booster" : 585673141125251097,
        "steelers" : 585994959807709217,
        "bots" : 586022880979189760,
        "muted": 608518377010495533,
        "vcmuted": 608765782507388939,
        "moderators" : 585676143798255616
        }
           
           
REACTS = {
        "partner": 608507177602121752,
        "hypesquad": 608507178931978260,
        "staff": 608507179871502346,
        "delete": 608507180840255499,
        "24mute": 608507181934968832,
        "48mute": 608507182803058698,
        "mute": 608507183725936650,
        "ban": 608507186095718409,
        "check": 608507187664519178,
        "no": 608507188780072981,
        "colts": 585628468515962888,
        "vikings": 585628468536934402,
        "texans": 585628468570619935,
        "jets": 585628468583333889,
        "rams": 585628468612694023,
        "broncos": 585628468625145858,
        "lions": 585628468696580097,
        "titans": 585628468767883286,
        "patriots": 585628468809564209,
        "chargers": 585628468809826315,
        "cowboys": 585628468813889547,
        "dolphins": 585628468927135744,
        "cardinals": 585628468931461150,
        "saints": 585628468935393280,
        "raiders": 585628468935655444,
        "bengals": 585628468943781893,
        "falcons": 585628468948107304,
        "panthers": 585628468956495872,
        "49ers": 585628468964884495,
        "jaguars": 585628468965015562,
        "redskins": 585628468977598474,
        "browns": 585628468981792790,
        "buccaneers": 585628468989919252,
        "bills": 585628468998569985,
        "steelers": 585628469015347230,
        "bears": 585628469019279388,
        "seahawks": 585628469023473664,
        "giants": 585628469031993352,
        "eagles": 585628469044576258,
        "nfl": 585628469048901682,
        "chiefs": 585628469078130698,
        "ravens": 585628469095038976,
        "packers": 585628469237383188,
        "at": 585629287516733456
        }

ROLE_REACT_MAP = {
                REACTS["seahawks"] : ROLES["seahawks"],
                REACTS["49ers"] : ROLES["49ers"],
                REACTS["rams"] : ROLES["rams"],
                REACTS["cardinals"] : ROLES["cardinals"],
                REACTS["buccaneers"] : ROLES["buccaneers"],
                REACTS["saints"] : ROLES["saints"],
                REACTS["panthers"] : ROLES["panthers"],
                REACTS["falcons"] : ROLES["falcons"],
                REACTS["vikings"] : ROLES["vikings"],
                REACTS["packers"] : ROLES["packers"],
                REACTS["lions"] : ROLES["lions"],
                REACTS["bears"] : ROLES["bears"],
                REACTS["redskins"] : ROLES["redskins"],
                REACTS["eagles"] : ROLES["eagles"],
                REACTS["giants"] : ROLES["giants"],
                REACTS["cowboys"] : ROLES["cowboys"],
                REACTS["jets"] : ROLES["jets"],
                REACTS["patriots"] : ROLES["patriots"],
                REACTS["dolphins"] : ROLES["dolphins"],
                REACTS["bills"] : ROLES["bills"],
                REACTS["browns"] : ROLES["browns"],
                REACTS["steelers"] : ROLES["steelers"],
                REACTS["bengals"] : ROLES["bengals"],
                REACTS["ravens"] : ROLES["ravens"],
                REACTS["titans"] : ROLES["titans"],
                REACTS["jaguars"] : ROLES["jaguars"],
                REACTS["colts"] : ROLES["colts"],
                REACTS["texans"] : ROLES["texans"],
                REACTS["raiders"] : ROLES["raiders"],
                REACTS["chargers"] : ROLES["chargers"],
                REACTS["chiefs"] : ROLES["chiefs"],
                REACTS["broncos"] : ROLES["broncos"],
                }

UNPROTECTED_ROLES = [role for role in ROLE_REACT_MAP.values()]


CHANS = { 'modchat': 585679916415188995,
          'modmail': 608510645167587328,
          'drama': 608510896800661514,
          'actions': 608510686552653865,
          'serverlog': 608510659407118338,
          'vclog': 608510712066867210,
          'tweets': 602712585355132945,
          'rules': 595702303105876083,
          'roleswap': 586019618116730880,
          'servernews': 595702445708017679,
          'feed': 608511598759378945,
          'genbotspam': 608511657517383680,
          'tweets': 608519059578945548
        }
        
CATS = {
        'mmnew': 608509238855073822,
        'mmreply': 608509238855073822,
        'mmwfr': 608509526135668746,
        'mmread': 608509526135668746,
        'mmgraveyard': 608509592506204160
        }

SERVERS = {
           'main': 90646584299118592,
           'ban': 00000000000000 # This server doesn't have a ban server so setting it to a fake ID should not affect any logic
          }

CAT_TRANSITION_ORDER = [608509238855073822, 608509526135668746, 608509592506204160]

CAT_TRANSITION = { 608509238855073822: 608509526135668746, # new / reply to wfr / closed
                   608509526135668746: 608509592506204160, # wfr / closed to graveyard
                   608509592506204160: "delete"            # graveyard to deletion
                 }
            
DISCORD_EPOCH = 1420070400000

MODMAIL_SYMBOLS = {"new":"▲",
                   "wfr":"○",
                   "reply":"●",
                   "read":"✓"
                  }

MSGS = {
        'action': '```\nAction: {action}\nUser(s):{username}#{discrim} ({id})\nReason: {reason}```{optional_content}',
        'msg_content_error': 'I\'ve deleted your message in {} since I have detected your message might not meet the channels guidelines! Please review the guidelines in the pins and if you feel your post should be allowed, feel free to use me to modmail to staff!',
        'banmsg': 'You have been banned from the Rhino Bot Help discord.',
        'dramaerror': 'Can\'t {} {} because they\'re not on the server.{}',
        'modmailaction': '→ I sent a message to {username} ({id}) {reason}, please refer to <#{action_log_id}> for more info',
        'modmailfirstime': '→ I sent a message to {username} ({id})  to remind them to read the welcome DM as they attempted to DM me without any roles',
        'warn': "**You have been warned on {server}** {reason}"
       }

MUTED_MESSAGES = {'timed': "You have been muted from communicating on this discord server for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. When your mutes time runs out, the role will be automatically removed and you'll have to return to <#{rules}> where you can once again pick up a role and rejoin the discussions. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future.",
                  'timed_over': "Your mute has ended but in order to regain access to the server you'd need to visit the <#{roles}> to reassign yourself a role. Also, please take the time to review the <#{rules}> channel to help prevent any further infractions.",
                  'plain': "You have been muted from communicating on this discord server. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future."}
                  
CBAN_MESSAGES = {'timed': "You have been temporarily banned from the {cban_name} channel(s) for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}> or within the rules of the channel(s). Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. When your mutes time runs out, the role will be automatically removed and you'll be able to rejoin the discussions. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future.",
                 'plain': "You have been banned from the {cban_name} channel(s). This has occurred due to you breaking one or more of the rules outlined in <#{rules}> or within the rules of the channel(s). Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future."}
                 
