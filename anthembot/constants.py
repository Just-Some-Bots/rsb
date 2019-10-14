ROLE_REACT_MSGS = [425803944803958795, 425803945164800001, 425803945919643648, 425803946401988618, 425803947148836865]
       
UNLOGGED_CHANNELS = []

REGEX = {'drama_base': r"(?<![\w])({})s?(?![\w])",
        'drama': '',
        'uplay': r"(?<![\w])(uplay|u play)(?![\w])", 
        'dox': r"(?<![\w])(?![\w])[!#$%&'*+./0-9=?_`a-z{|}~^-]+@[.a-z-]+\.(?:com|org|net)"
        }

REGEX['drama'] = REGEX['drama_base'].format('')
        
MM_CATS = {
           'mmnew': 608462067002769438,
           'mmreply': 608462067002769438,
           'mmwfr': 608462148678713374,
           'mmread': 608462148678713374,
           'mmgraveyard': 608462228085014538
           }
       
VC_CATS = { 'na': 531663194947584010,
            'eu': 531663231643680787,
            'other': 531663273616080926
           }
        
VC_CATS_REV = { 531663194947584010: 'na',
                531663231643680787: 'eu',
                531663273616080926: 'other'
               }  
       
VC_CAT_LFG_NAMING = { 'na': "[NA {}]",
                      'eu': "[EU {}]",
                      'other': "[OTH {}]"
                    }  

MM_CAT_TRANSITION_ORDER = [608462067002769438, 608462148678713374, 608462228085014538]

MM_CAT_TRANSITION = { 608462067002769438: 608462148678713374, # new / reply to wfr / closed
                      608462148678713374: 608462228085014538, # wfr / closed to graveyard
                      608462228085014538: "delete"            # graveyard to deletion
                    }
       
ROLES = { 'muted': 423028373103706112,
          'staff': 323202328804982785,
          'pc': 324325847312105491,
          'submods': 323196414907777046,
          'BW': 323546696120270849,
          'CMs': 534970048989626368,
          'ateveryone': 323187591702773763,
          'ps4': 324325359677997056,
          'testing': 583857041651662848,
          'xbox': 324325593044877312,
          'gamenews': 425771366923370501,
          'bots': 425729675617107988,
          'vcmuted': 425770226060099594,
          'colossus': 460136121549062165,
          'interceptor': 460136219288928266,
          'ranger': 460136224179486742,
          'storm': 460136225928380448,
          'freelancer': 323365132786860034,
          'cc': 325026182519193605,
          'jav': 539286473199976449,
          'lore': 537057548831031296,
          'servernews': 425771406127792128
          }

UNPROTECTED_ROLES = [ROLES['jav'], ROLES['servernews'], ROLES['muted'], ROLES['pc'], ROLES['ateveryone'], ROLES['ps4'], ROLES['xbox'], ROLES['gamenews'], ROLES['lore'], ROLES['colossus'], ROLES['interceptor'], ROLES['ranger'], ROLES['storm'], ROLES['freelancer']]
           
REACTS = { 'delete': 425724774036144139,
           'mute': 425724776418508801,
           '24mute': 425724768793264128,
           '48mute': 425724765177905193,
           'ban': 425724772400234520,
           'check': 425804644099424257,
           'no': 426768929172488194,
           'pc': 460795459783360524,
           'ps4': 460795460706107422,
           'xbox': 460795460706369536,
           'freelancer': 324522409245802496,
           'colossus': 539291510034661397,
           'interceptor': 539291170770124821,
           'ranger': 539291171265052693,
           'storm': 539291171130834954,
           'jav': 557663996644163597,
           'testing': 557663940381769760,
           'gameping': 323869642118529026,
           'lore': 519031038329094144,
           'serverping': 425789229361135617
        }


CHANS = { 'admins': 324066335783124992,
          'staff': 529024803081027584,
          'modmail': 373787435995234305,
          'drama': 460798145236959232,
          'actions': 422762982938771478,
          'rules': 323187591702773763,
          'cc': 327271342879539200,
          'serverlog': 422763009409155072,
          'muted': 0000000000000,
          'vclog': 373787775146655745,
          'twitch': 538297600558759936,
          'tweets': 330537414558875648,
          'roleswap': 373787547249278976,
          'servernews': 361289536753631232,
          'gamenews': 323197630056366080,
          'rolereminder': 0000000000000,
          'lfgnapc': 531663316683063309,
          'lfgnaxbox': 531663374828699691,
          'lfgnaps4': 531663375986458634,
          'lfgeupc': 531663231643680787,
          'lfgeuxbox': 531663737501908992,
          'lfgeups4': 531663784784429066,
          'lfgotherpc': 531663809874624522,
          'lfgotherxbox': 531663843068346368,
          'lfgotherps4': 531663860772634634,
          'spoiled': 519027023432253440,
          'registration': 324097483745787904
          }
        
SERVERS = {
           'main': 323187591702773763,
           'ban': 425721024101875712
          }

MODMAIL_SYMBOLS = {"new":"▲",
                   "wfr":"○",
                   "reply":"●",
                   "read":"✓"
                  }
            
DISCORD_EPOCH = 1420070400000

LFG_CHANS = [ CHANS['lfgnapc'], CHANS['lfgnaps4'], CHANS['lfgnaxbox'], CHANS['lfgeupc'], CHANS['lfgeups4'], CHANS['lfgeuxbox'], CHANS['lfgotherpc'], CHANS['lfgotherxbox'], CHANS['lfgotherps4'] ]

MSGS = {
        'action': '```\nAction: {action}\nUser(s):{username}#{discrim} ({id})\nReason: {reason}```{optional_content}',
        'msg_content_error': 'I\'ve deleted your message in {} since I have detected your message might not meet the channels guidelines! Please review the guidelines in the pins and if you feel your post should be allowed, feel free to use me to modmail the staff!',
        'lfg_length': "I've deleted your message in {} since I have detected your message is over 200 characters long and may not be about trying to find a group. Please review the guidelines in the pins and if you feel your post should be allowed, feel free to use me to modmail the staff!",
        'banmsg': 'You have been banned from the /r/AnthemTheGame discord. If you wish to appeal this ban, please fill out this form:\n<https://goo.gl/forms/VklLDrqksajZfdwt1>',
        'dramaerror': 'Can\'t {} {} because they\'re not on the server.{}',
        'modmailaction': '→ I sent a message to {username} ({id}) {reason}, please refer to <#{action_log_id}> for more info',
        'modmailfirstime': '→ I sent a message to {username} ({id})  to remind them to read the welcome DM as they attempted to DM me without any roles',
       }

ROLE_ALIASES = {'computer': 324325847312105491,
                'xboxone': 324325593044877312,
                'xbox one': 324325593044877312,
                'play station': 324325359677997056,
                'playstation': 324325359677997056,
                'ps4': 324325359677997056,
                'psn': 324325359677997056,
                'x1': 324325593044877312,
                'xb1': 324325593044877312
                }

MUTED_MESSAGES = {'timed': "You have been muted from communicating on this discord server for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. When your mutes time runs out, the role will be automatically removed and you'll have to return to <#{rules}> where you can once again pick up a new platform role and rejoin the discussions. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future. ",
                  'timed_over': "Your mute has ended but in order to regain access to the server you'd need to visit the <#{roles}> to reassign yourself a platform role. Also, please take the time to review the <#{rules}> channel to help prevent any further infractions.",
                  'plain': "You have been muted from communicating on this discord server. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future."}

WARN_MSG = "**You have been warned on {server}** {reason}"

CBAN_MESSAGES = {'timed': "You have been temporarily banned from the {cban_name} channel(s) for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}> or within the rules of the channel(s). Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. When your mutes time runs out, the role will be automatically removed and you'll be able to rejoin the discussions. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future.",
                 'plain': "You have been banned from the {cban_name} channel(s). This has occurred due to you breaking one or more of the rules outlined in <#{rules}> or within the rules of the channel(s). Replying to this message in DMs will allow you to communicate with staff and to get clarification on what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. Spamming DMs or being rude to staff will have you permanently banned. If you have any questions, you can ask via a DM to the bot (me), but do so in a respectful manner and remember to follow the rules in the future."}

