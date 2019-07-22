UNPROTECTED_ROLES = [602708843536842764, 602778201852477450, 136305705635282944]

UNLOGGED_CHANNELS = [132677532766961665, 157598062020132865]

REGEX = {'drama_base': r"(?<![\w])({})s?(?![\w])",
        'drama': '',
        'uplay': r"(?<![\w])(uplay|u play)(?![\w])", 
        'dox': r"(?<![\w])(?![\w])[!#$%&'*+./0-9=?_`a-z{|}~^-]+@[.a-z-]+\.(?:com|org|net)"
        }

REGEX['drama'] = REGEX['drama_base'].format('')
       
ROLES = { 'muted': 136305705635282944,
          'devs': 169846694475857921,
          'help': 129667505923948544,
          'music': 602708843536842764,
          'rsb': 602778201852477450,
          'competent': 141850985323560960,
          'bots': 129490028333236224,
          'cool': 136931690395205632,
          'nb': 582240786037342211,
          'vcmuted': 602726932945305610,
          'ateveryone': 129489631539494912,
          }
           
           
REACTS = { 'delete': 602718128056827917,
           '24mute': 602718143663833150,
           '48mute': 602718157098057729,
           'mute': 602718174475190283,
           'ban': 602718185611067403,
           'check': 602718202304135168,
           'no': 602718213561778176,
           'partner': 602710563793141770,
           'hypesquad': 602710637319159818,
           'staff': 602711765192671242,
           'music': 602780824018092057,
           'rsb': 602779483979776011
        }


CHANS = { 'devchat': 132677532766961665,
          'vipchat': 157598062020132865,
          'modmail': 602712535376068645,
          'drama': 602712335198453761,
          'actions': 602712388818567168,
          'serverlog': 602712402366169098,
          'vclog': 602712649410543646,
          'twitch': 602712620277170178,
          'tweets': 602712585355132945,
          'rules': 143331575679942656,
          'roleswap': 602712813303103528,
          'servernews': 143334341500600320,
          'genbotspam': 134771894292316160,
          'notifications': 602721843325173770
        }
        
CATS = {
        'mmnew': 602713381551603712,
        'mmreply': 602713381551603712,
        'mmwfr': 602713551165063198,
        'mmread': 602713551165063198,
        'mmgraveyard': 602713624385159178
        }

VC_CATS = { 'vc_cat': 602722404430512128 }
        
CATS_REV = { 602722404430512128: 'vc_cat' }  
       
CAT_LFG_NAMING = { 'vc_cat': "Channel {}" }

SERVERS = {
           'main': 129489631539494912,
           'ban': 00000000000000 # RhinoBotHelp doesn't have a ban server so setting it to a fake ID should not affect any logic
          }

CAT_TRANSITION_ORDER = [602713381551603712, 602713551165063198, 602713624385159178]

CAT_TRANSITION = { 602713381551603712: 602713551165063198, # new / reply to wfr / closed
                   602713551165063198: 602713624385159178, # wfr / closed to graveyard
                   602713624385159178: "delete"            # graveyard to deletion
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
                 
