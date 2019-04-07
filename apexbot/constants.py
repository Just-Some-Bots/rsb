REGEX = {
        'drama': r"(?<![\w])((sand)?nig(ger|ga)?|twitch.tv/.*|recruit(ing|in|ment)?|towelhead|twat|chink|beaner|dyke|jew|kike|tranny|cunt|cuck|spic|faggot|fag|SJW|retard(ed)?|fuck you|queer|coon|shemale|rape(ed)?|nazi|hitler|autist(ic)?|trump|fanbo.*|kill (yo)?urself|kys)s?(?![\w])",
        'drama2': r"(?<![\w])((sand)?nig(ger|ga)?|towelhead|twat|chink|beaner|dyke|jew|kike|tranny|cunt|cuck|spic|faggot|fag|SJW|retard(ed)?|fuck you|queer|coon|shemale|rape(ed)?|nazi|hitler|autist(ic)?|trump|fanbo.*|kill (yo)?urself|kys)s?(?![\w])",
        'dox': r"(?<![\w])(?![\w])[!#$%&'*+./0-9=?_`a-z{|}~^-]+@[.a-z-]+\.(?:com|org|net)"
       }
       
TEXT_CATS = { 'na': 542415274544988182,
         'eu': 542415434599628801,
         'oce': 542415712229130297,
         'sea': 543049006427668500,
         'latam': 543053590756065300
        }
        
TEXT_CATS_REV = { 542415274544988182: 'na',
             542415434599628801: 'eu',
             542415712229130297: 'oce',
             543049006427668500: 'sea',
             543053590756065300: 'latam'
            }
            
VC_CATS = { 'na': 542557896731394060,
         'na_empty': 543224985490030594,
         'na3': 543225292509151262,
         'na2': 543113889626324994,
         'eu_empty': 543228649357180947,
         'eu': 542564750706475008,
         'eu2': 542868826342293504,
         'oce': 542560925803085830,
         'sea': 543046676491927567,
         'latam': 543047909554388992
        }
       
EMPTY_TO_MAIN = { 543224985490030594: 542557896731394060,
                   543228649357180947: 542564750706475008
                 }  
       
MAIN_TO_EMPTY = { 542557896731394060: 543224985490030594,
                   543113889626324994: 543224985490030594,
                   543225292509151262: 543224985490030594,
                   542564750706475008: 543228649357180947,
                   542868826342293504: 543228649357180947
                 }  

EMPTY_CATS = [VC_CATS['na_empty'], VC_CATS['eu_empty']]
LOOP_CATS = [VC_CATS['oce'], VC_CATS['sea'], VC_CATS['latam']]
OVERSPILL_CATS = [VC_CATS['na2'], VC_CATS['na3'], VC_CATS['eu2']]
DOUBLE_SORTED_CATS = [VC_CATS['na'], VC_CATS['eu']]
        
MAIN_TO_OVERSPILL_CATS = { 542557896731394060: 543113889626324994,
                           543113889626324994: 543225292509151262,
                           542868826342293504: None,
                           542564750706475008: 542868826342293504
                         }
        
OVERSPILL_TO_MAIN_CATS = { 543113889626324994: 542557896731394060,
                           543225292509151262: 543113889626324994,
                           542868826342293504: 542564750706475008
                         }
            
VC_CATS_REV = { 542557896731394060: 'na',
             543113889626324994: 'na2',
             543225292509151262: 'na3',
             543224985490030594: 'na_empty',
             542564750706475008: 'eu',
             542868826342293504: 'eu2',
             543228649357180947: 'eu_empty',
             542560925803085830: 'oce',
             543046676491927567: 'sea',
             543047909554388992: 'latam'
            }  
       
CAT_LFG_NAMING = { 'na': "[NA] Team {}",
                   'na2': "[NA] Team {}",
                   'na3': "[NA] Team {}",
                   'na_empty': "[NA] Team {}",
                   'eu': "[EU] Team {}",
                   'eu2': "[EU] Team {}",
                   'eu_empty': "[EU] Team {}",
                   'oce': "[OCE] Team {}",
                   'sea': "[SEA] Team {}",
                   'latam': "[LATAM] Team {}"
                 }  
       
ROLES = { 'muted': 542778295599497216,
          'staff': 542124834948251648,
          'pc': 542119867587887134,
          'ps4': 542119895178018817,
          'xbox': 542119908964827136,
          'submods': 543059516393259019,
          'Respawn': 542018236405907466,
          'modmail': 542793556734115892,
          'zepp': 542739980481593354,
          'apexpartner': 542256718546075668
          }
           
REACTS = { 'delete': 543091047316717588,
           'mute': 543091139323101187,
           '24mute': 543091084444696577,
           '48mute': 543091113318154270,
           'ban': 543091609592659988,
           'check': 543091661010501645,
           'no': 543089557260992542
        }


CHANS = { 'staff': 542458760438874128,
          'drama': 543092411950170112,
          'muted': 543020770700296213,
          'staff_bot': 542742664165195787,
          'rules': 542257503816384524,
          'vclog': 542821318408667136,
          'twitch': 00000000000000000,
          'tweets': 00000000000000000,
          'lfgnapc': 542118303225741334,
          'lfgnaxbox': 542118405285740544,
          'lfgnaps4': 542118387879510057,
          'lfgeupc': 542454951079706624,
          'lfgeuxbox': 542455397005656084,
          'lfgeups4': 542455121511055370,
          'lfgocepc': 542455070965366796,
          'lfgocexbox': 542455149889585178,
          'lfgoceps4': 542455137818378241,
          'lfgseapc': 543049041735581698,
          'lfgseaxbox': 543049265644175360,
          'lfgseaps4': 543049345080098816,
          'lfgsapc': 543053620686618645,
          'lfgsaxbox': 543053769097740288,
          'lfgsaps4': 543053829801902090
          }
        
SERVERS = {
           'main': 541484311354933258,
           'ban': 542668204120473610
          }
            
DISCORD_EPOCH = 1420070400000

LFG_CHANS = [ CHANS['lfgnapc'], CHANS['lfgnaps4'], CHANS['lfgnaxbox'], CHANS['lfgeupc'], CHANS['lfgeups4'], CHANS['lfgeuxbox'], CHANS['lfgocepc'], CHANS['lfgocexbox'], CHANS['lfgoceps4'], CHANS['lfgseapc'], CHANS['lfgseaxbox'], CHANS['lfgseaps4'], CHANS['lfgsapc'], CHANS['lfgsaxbox'], CHANS['lfgsaps4']]

MSGS = {
        'cban_message': '{user_mention} You have been channel banned from the {cban_role} channels(s). If you\'d like to appeal, please message <@!542736472155881473>.',
        'timed_cban_message': '{user_mention} You have been channel banned from the {cban_role} channels(s) for {time}. If you\'d like to appeal, please message <@!542736472155881473>.',
        'lfg_awareness': 'A heads up for those who don\'t know, you can create a post with a URL that leads directly to your voice channel by using the `!lfg` command!\nExample: !lfg Hey I\'m new but looking for people who wanna hang out!\n\nThere is also `!inv` which will DM you the invite url for your current channel and more, just look in this channels pins for more info!',
        'dramaerror': 'Can\'t {} {} because they\'re not on the server.{}',
       }