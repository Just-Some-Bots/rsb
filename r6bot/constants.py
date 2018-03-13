UNPROTECTED_ROLES = [253581140072464384, 253583191732912129, 253583702162931723, 253583831557341184, 357592666340458497, 357592486455017473, 412954620961226763]

SUDO_ROLES = [253582130460753921, 253581597641670657, 269511788192595969, 278967111454556170, 278980438754590731, 286363905544945664]

ROLE_REACT_MSGS = [412964933920358407, 412964933685477376, 412964934570344458, 412964934625001473]

REGEX = {'drama': r"(?<![\w])(nig(ger|ga)?|towelhead|twat|chink|beaner|dyke|jew|kike|tranny|cunt|cuck|spic|faggot|fag|SJW|retard(ed)?|fuck you|queer|coon|shemale|rape(ed)?|nazi|hitler|autist(ic)?|trump|fanbo.*|kill (yo)?urself|kys)s?(?![\w])",
       'uplay': r"(?<![\w])(uplay|u play)(?![\w])", 
       'dox': r"(?<![\w])(?![\w])[!#$%&'*+./0-9=?_`a-z{|}~^-]+@[.a-z-]+\.(?:com|org|net)"
       }
       
ROLES = { 'muted': 279039481875529729,
          'staff': 278967111454556170,
          'pc': 253583191732912129,
          'ateveryone': 253581140072464384,
          'ps4': 253583831557341184,
          'xbox': 253583702162931723,
          'r6news': 357592666340458497,
          'bots': 278980438754590731,
          'banteams': 351548451718430721,
          'seriousd': 279746737596399617,
          'vcmuted': 332255104822673408,
          'invitationals': 412954620961226763,
          'servernews': 357592486455017473
          }
           
           
REACTS = { 'delete': 365466529065598976,
           'mute': 365466529074118656,
           '24mute': 365463284108754944,
           '48mute': 365463283777667074,
           'ban': 365466528973455361,
           'pc': 357583145643540480,
           'ps4': 357584218903281664,
           'xbox': 357583628634685440,
           'invitationals': 347822883122446336,
           'r6ping': 361727658154786826,
           'serverping': 357595858432163840
        }


CHANS = { 'staff': 276407407117074432,
          'modmail': 279356892193751041,
          'drama': 365448564261912576,
          'actions': 279327718368083968,
          'rules': 286359381841412098,
          'watch': 314827694200061953,
          'serverlog': 269545820326461441,
          'muted': 286369301600927747,
          'vclog': 279522178515337216,
          'twitch': 271403816497184768,
          'roleswap': 357581480110850049,
          'servernews': 280884809486827520,
          'gamenews': 270315303257243649,
          'rolereminder': 358275617495580673,
          'registration': 278959675888893952,
          'twitchinvupdates': 412426123587354625,
          'scrimspc': 290274342904922112,
          'scrimsps4': 380632834437808129,
          'scrimsxbox': 380633112394072064,
          'plftpc': 290428408465195008,
          'plftps4': 290428617773678592,
          'plftxbox': 290428645883772928,
          'tlfppc': 290428366312701962,
          'tlfpps4': 290428522080763904,
          'tlfpxbox': 290428554968301569,
          'lfgnapc': 269519917693272074,
          'lfgnaps4': 282076089927598081,
          'lfgnaxbox': 282076117651947520,
          'lfgeupc': 269566972977610753,
          'lfgeups4': 282076300838043648,
          'lfgeuxbox': 282076329829072897,
          'lfganzpc': 282076880285204480,
          'lfganzps4': 282076800698548224,
          'lfganzxbox': 282076856201510914,
          'lfgseaspc': 269567077805719552,
          'lfgseasps4': 282076615784136705,
          'lfgseasxbox': 282076628153139200,
          'ubireports': 360541244570468353,
          'registration': 278959675888893952,
          'registration': 278959675888893952,
          'registration': 278959675888893952,
          'registration': 278959675888893952,
          'genbotspam': 278986547187941377
        }
        
SERVERS = {
           'main': 253581140072464384,
           'ban': 350379919806824449
          }
          
PLAYER_LF_TEAM_CHANS = [ CHANS['plftpc'], CHANS['plftps4'], CHANS['plftxbox'] ]

TEAM_LF_PLAYER_CHANS = [ CHANS['tlfppc'], CHANS['tlfpps4'], CHANS['tlfpxbox'] ]

TEAM_CHANS = PLAYER_LF_TEAM_CHANS + TEAM_LF_PLAYER_CHANS

SCRIM_CHANS = [ CHANS['scrimspc'], CHANS['scrimsps4'], CHANS['scrimsxbox'] ]

LFG_CHANS = [ CHANS['lfgnapc'], CHANS['lfgnaps4'], CHANS['lfgnaxbox'], CHANS['lfgeupc'], CHANS['lfgeups4'], CHANS['lfgeuxbox'], CHANS['lfganzpc'],
              CHANS['lfganzps4'], CHANS['lfganzxbox'], CHANS['lfgseaspc'], CHANS['lfgseasps4'], CHANS['lfgseasxbox'] 
            ]
            
DISCORD_EPOCH = 1420070400000

MSGS = {
        'action': '```\nAction: {action}\nUser(s):{username}#{discrim} ({id})\nReason: {reason}```{optional_content}',
        'msg_content_error': 'I\'ve deleted your message in {} since I have detected your message might not meet the channels guidelines! Please review the guidelines in the pins and if you feel your post should be allowed, feel free to use me to modmail to staff!',
        'banmsg': 'You have been banned from the Rainbow6 discord. If you wish to appeal this ban, please fill out this form:\n<https://goo.gl/forms/kSVm0dfdO075PAOB2>',
        'softbanmsg': 'You have been kicked from the Rainbow6 discord and all of your messages removed.',
        'dramaerror': 'Can\'t {} {} because they\'re not on the server.{}',
        'modmailaction': '→ I sent a message to {username} ({id}) {reason}, please refer to <#{action_log_id}> for more info',
        'modmailfirstime': '→ I sent a message to {username} ({id})  to remind them to read the welcome DM as they attempted to DM me without any roles',
       }

ROLE_ALIASES = {'computer': 253583191732912129,
                'xboxone': 253583702162931723,
                'xbox one': 253583702162931723,
                'play station': 253583831557341184,
                'playstation': 253583831557341184,
                'ps4': 253583831557341184,
                'x1': 253583702162931723,
                'xb1': 253583702162931723
                }

MUTED_MESSAGES = {'timed': "You have been muted from communicating on this discord server for {time}. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. The channel <#{muted}> is for you to communicate with staff to clarify what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. We have the channel as a courtesy to our users, as we use the channel instead of outright banning people. Spamming in the muted chat or being rude to staff will have you permanently banned.When your mutes time runs out, the role will be automatically removed and you'll have to return to <#{rules}> where you can once again pick up a new platform role and rejoin the discussions. If you have any questions, you can mention a discord staff member, but do so in a respectful manner and remember to follow the rules in the future. ",
               'plain': "You have been muted from communicating on this discord server. This has occurred due to you breaking one or more of the rules outlined in <#{rules}>. The channel <#{muted}> is for you to communicate with staff to clarify what you did wrong to avoid the problem in the future. It is not the place to try to shorten the duration of your mute or get out of it. We have the channel as a courtesy to our users, as we use the channel instead of outright banning people. Spamming in the muted chat or being rude to staff will have you permanently banned. If you have any questions, you can mention a discord staff member, but do so in a respectful manner and remember to follow the rules in the future."}