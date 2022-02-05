#!/usr/bin/env python3
import subprocess, frida, shutil
import cmd, os, sys, platform
import readline, logging, time, rlcompleter
from libraries.Questions import Polar
from libraries.libguava import *
from libraries.Questions import *
from colorama import Fore, Back, Style

BASE = os.path.dirname(__file__) 

APKTOOL = os.path.abspath(os.path.join(BASE,'../dependencies/apktool.jar'))
APK_SIGNER =os.path.abspath(os.path.join(BASE,'../dependencies/apksigner')) 
ZIPALLIGN = os.path.abspath(os.path.join(BASE,'../dependencies/zipalign')) 
DEBUGGABLE_APK = os.getcwd()+"/debuggable.apk"
ALLIGNED_APK = os.getcwd()+"/debuggable_alligned_signed.apk"
TMP_FOLDER = os.getcwd()+"/tmp_dir"
SIGNATURE = os.path.abspath(os.path.join(BASE,'../dependencies/common.jks')) 



readline.set_completer_delims(readline.get_completer_delims().replace('/', ''))
BUSSY_BOX_URL = "https://busybox.net/downloads/binaries/1.31.0-defconfig-multiarch-musl/"

HELP_MESSAGE = Style.BRIGHT + "\nSYNOPSIS:"+Style.RESET_ALL+"""
    mango>[command] <parameters> <flags>""" +Style.BRIGHT +"""

DESCRIPTION"""+Style.RESET_ALL+"""

    mango is a MEDUSA's tentacle which helps analysers to extract and analyse 'static' components of and Android
    Application. The results are saved to a SQLite database which can be reloaded or updated with new samples. 
    Additionally, it automates various other tasks, like changing proxy settings on the device, force to 
    start/stop services, install/uninstall applications, take screenshots and many more."""+ Style.BRIGHT+"""

    The options are as follows:"""+Style.RESET_ALL+"""

    adb                         Start an interactive adb prompt.

    box                         Starts a busybox interactive shell. 

    c                           Run a local shell command.
                                (Example: > c ls -al ./)

    cc                          Run a command using the default adb shell.
                                (Example: > cc ls -al /sdcard)

    exit                        Exits the application.

    help                        Displays this text. 

    import                      Imports an apk file for analysis and saves the results to the session's database. 
                                (Example: > import /path/to/foo.apk)

    installBurpCert             Install the Burp certificate to the mobile device. 

    jdwp                        Create a jdb session. Use it in combination with the tab key to see available packages. 
                                The app has to have the debuggable flag to true.

    notify                      Sends a notification to the device (it is used to trigger notification listeners). The
                                Medusa Agent must be installed and running on the device (see installagent).
                                (Example: > notify 'Title' 'Lorem ipsum dolor sit amet,....')

    patch                       Changes the debuggable flage of the AndroidManifest.xml to true for a given apk.
                                (Example: > patch /path/to/foo.apk)

    proxy                       Performs a proxy modification or reads a proxy setting (used for MITM). If adb runs as 
                                root it can be used with the '-t' flag to set a transparent proxy. 
                                (Example: > proxy set 192.168.1.2:8080 -t)

    pull                        Extracts an apk from the device and saves it as 'base.apk' in the working directory.
                                Use it in combination with the tab key to see available packages
                                (Example: > pull com.foo.bar)

    query                       Performs a raw query in the session db and returns the results as a list of tuples.
                                (Example: > query SELECT * FROM Application)

    screencap                   Captures the device screen and saves it as a png file in the current directory. 
                                (Example: > screencap -o 'screen1.png')
    
    search                      Searches for a given string in the extracted components and strings.
                                (Example: search foobar)

    show                        Prints information about components of the loaded application. The currently available
                                are: activities, services, activityAlias, receivers, deeplinks, providers and 
                                intentFilters. Adding the '-e' flag will print only exported components. Additionaly
                                'database' prints the database structure of the session database, 'manifest' the prints
                                the manifest and 'info' prints general information about the loaded application. 
                                (Example: > show activities -e)
                                
    start                       Forces to start an activity of the loaded application. Use it in combination with the 
                                tab key to see the available activities. For non exported activities, the adb must run 
                                with root privileges. 

    swap                        Loads an apk analysis that is already availlable in the session db.

    startsrv, stoprsrv          Forces to start or stop a service of the loaded application. Use it in combination with 
                                the tab key to see the available services. For non exported services, the adb must run 
                                with root privileges.

    uninstall, kill, spawn      Uninstalls, kills or starts an app in the device. Use it in combination with the tab 
                                key to see available packages.
                                (Example: > uninstall com.foo.bar , > kill com.foo.bar1)"""

RED   = "\033[1;31m"  
BLUE  = "\033[1;34m"
CYAN  = "\033[1;36m"
WHITE = "\033[1;37m"
YELLOW= "\033[1;33m"
GREEN = "\033[0;32m"
RESET = "\033[0;0m"
BOLD    = "\033[;1m"
REVERSE = "\033[;7m"
current_dir = os.getcwd()

class parser(cmd.Cmd):
    NO_APP_LOADED_MSG = "[i] No application is loaded, type 'import /path/to/foo.apk' to load one"

    base_directory = os.path.dirname(__file__)
    prompt = Fore.BLUE +Style.BRIGHT +'mango> '+Fore.RESET+Style.RESET_ALL
    current_app_sha256 = None
    database =None
    guava = None
    INSTALL = False
    device = None
    package = None
    permissions = None
    activities = None
    activity_names = None
    service_names = None
    activityallias = None
    info = None
    services = None
    receivers = None
    providers = None
    deeplinks = None
    intent_filters = None
    hosts = set()
    schemes = set()
    pathPrefixes = set()
    manifest = None

    strings = []
    packages = []


    def continue_session(self,guava):
        self.guava = guava
        res = self.database.query_db("SELECT sha256, packageName from Application;")
        if res:
            print(Fore.GREEN+"[i] Availlable applications:\n" +Fore.RESET +"-"*7+" "+"-"*70+" "+"-"*57+"\n {0} {1:^68} {2:^60}\n".format("index","sha256","Package Name")+"-"*7+" "+"-"*70+" "+"-"*57)
            index = 0
            for entry in res:
                sha256, package_name = entry
                print(Fore.CYAN+Style.BRIGHT+"{0:^7} {1:^68} {2:^60}".format(index,sha256,package_name))
                index+=1
            
            chosen_index = int(Numeric(Style.RESET_ALL+'\nEnter the index of  application to load:', lbound=0,ubound=index-1).ask())
            chosen_sha256 = res[chosen_index][0]
            self.init_application_info(self.database,chosen_sha256)
        

        else:
            print(Fore.RED+Style.BRIGHT+ "[!] No Entries found in the given database !"+Style.RESET_ALL)
        return

    
    def init_application_info(self,application_database,app_sha256):

        try:
            self.info = application_database.get_app_info(app_sha256)
            self.print_application_info(self.info)
            self.activities = application_database.get_all_activities(app_sha256)
            self.permissions = application_database.get_all_permissions(app_sha256)
            self.services = application_database.get_all_services(app_sha256)  
            self.activityallias = application_database.get_all_alias_activities(app_sha256)
            self.receivers = application_database.get_all_receivers(app_sha256)
            self.providers = application_database.get_all_providers(app_sha256)
            self.intent_filters = application_database.get_intent_filters(app_sha256)
            self.activity_names = list('\n'.join(map(lambda x: str(x[0]), application_database.query_db("SELECT name from Activities WHERE app_sha256='{}'".format(app_sha256)))).split('\n'))
            self.service_names = list('\n'.join(map(lambda x: str(x[0]), application_database.query_db("SELECT name from Services WHERE app_sha256='{}'".format(app_sha256)))).split('\n'))
            self.manifest = application_database.query_db("SELECT androidManifest FROM Application WHERE sha256='{}';".format(app_sha256))
            self.strings = application_database.query_db("SELECT stringResources FROM Application WHERE sha256='{}';".format(app_sha256))[0][0].decode('utf-8')
            self.deeplinks = application_database.get_deeplinks(app_sha256)
            self.print_deeplinks(True) #propagate the deeplink lists
            self.current_app_sha256 = app_sha256
        except Exception as e:
            print(e)


    def print_application_info(self,info):
        
        print(Back.BLACK+Fore.RED+Style.BRIGHT+"""
[------------------------------------Package Details---------------------------------------]:
|    Application Name  :{}
|    Package Name      :{}
|    Version code      :{}
|    Version Name      :{}
|    Mimimum SDK       :{}
|    Target  SDK       :{}
|    Max SDK           :{}
|    Sha256            :{}
|    Debuggable        :{}
|    Allow Backup      :{} 
[------------------------------------------------------------------------------------------]
|                          Type 'help' for a list of commands                              |
[------------------------------------------------------------------------------------------]
        """.format(info[0][1],info[0][2],info[0][3],info[0][4],
            info[0][5],info[0][6],info[0][7],info[0][0],info[0][10],info[0][11]) +Style.RESET_ALL)   



    def print_activity_alias(self,all = True):

        display_text = ''
        for attribs in self.activityallias:
            display_text = attribs[1]
            if attribs[2]:
                display_text += Fore.RED + ' | enabled = '+attribs[2]+' |' + Fore.RESET
            if attribs[3]:
                display_text += Fore.GREEN + ' | exported = '+attribs[3]+' |' + Fore.RESET
            if attribs[5]:
                display_text += Fore.CYAN + ' | Target = '+attribs[5] + Fore.RESET

            if (not all) and (not attribs[3] or (not 'true' in attribs[3])):
                continue
            else:
                print(display_text)
        print(Style.RESET_ALL)


    
    def print_deeplinks(self,quite=False):

        display_text = ''
        component = ''
        lst = []
        for attribs in self.deeplinks:
            if component != attribs[0]:
                component = attribs[0]
                l = len(component)
                if not quite:
                    print(Fore.GREEN+'-'*l+'\nComponent:{}'.format(component)+Fore.RESET)

            detonate = attribs[1].split('|')

            schemes = ''
            lst.clear()
            for ingredient in detonate:
                if 'scheme:' in ingredient:
                    t = ingredient.split(':')[1]
                    schemes += t
                    schemes += ' '
                    lst.append(t)
            
                self.schemes =set.union(self.schemes,set(lst))
    
        
            if not quite:
                print("Schemes: "+schemes)

            hosts = ''
            lst.clear()
            for ingredient in detonate:
                if 'host:' in ingredient:
                    j = ingredient.split(':')[1]
                    hosts += j
                    hosts += ' '
                    lst.append(j)

                self.hosts = set.union(self.hosts,set(lst))

            if not quite:
                print("Hosts: "+hosts)

            pathPrefix = ''
            lst.clear()
            for ingredient in detonate:
                if 'pathPrefix:' in ingredient:
                    p = ingredient.split(':')[1]
                    pathPrefix += p
                    pathPrefix += ' '
                    lst.append(p)
                self.pathPrefixes = set.union(self.pathPrefixes,set(lst))
            
            if not quite:
                print("pathPrefix: "+pathPrefix)
  



    def print_activities(self,all = True):

        display_text = ''
        for attribs in self.activities:
            display_text = attribs[1]
            if attribs[2]:
                display_text += Fore.RED + ' | enabled = '+attribs[2]+' |' + Fore.RESET
            if attribs[3]:
                display_text += Fore.GREEN + ' | exported = '+attribs[3]+Fore.RESET
            if (not all) and (not attribs[3] or (not 'true' in attribs[3])):
                continue
            else:
                print(display_text)
        print(Style.RESET_ALL)


    def print_intent_filters(self):
        display_text = ''
        for attribs in self.intent_filters:
            l = len(attribs[0])
            print(Fore.GREEN+'-'*l+'\nComponent:{}'.format(attribs[0])+Fore.RESET)
         
            if attribs[1]:
                print('Action(s): '+attribs[1].replace('|',' # '))
            if attribs[2]:
                print('Category: '+attribs[2].replace('|',' # '))
     
  
            print(Fore.GREEN+'-'*l+Fore.RESET)
            


        print(Style.RESET_ALL)
    
    def print_providers(self,all = True):

        display_text = ''
        for attribs in self.providers:
            display_text = attribs[1]
            if attribs[2]:
                display_text += Fore.RED + ' | enabled = '+attribs[2]+' |' + Fore.RESET
            if attribs[3]:
                display_text += Fore.GREEN + ' | exported = '+attribs[3]+' |' + Fore.RESET
            if attribs[4]:
                display_text += Fore.CYAN + ' | grandUriPermission = '+attribs[4] + Fore.RESET
            if attribs[9]:
                display_text += Fore.CYAN + ' | authorities = '+attribs[9] + Fore.RESET

            if (not all) and (not attribs[3] or (not 'true' in attribs[3])):
                continue
            else:
                print(display_text)
        print(Style.RESET_ALL)
    
    def print_receivers(self,all = True):
        display_text = ''
        for attribs in self.receivers:
            display_text = attribs[1]
            if attribs[2]:
                display_text += Fore.RED + ' | enabled = '+attribs[2]+' |' + Fore.RESET
            if attribs[3]:
                display_text += Fore.GREEN + ' | exported = '+attribs[3]+' |' + Fore.RESET
            if attribs[4]:
                display_text += Fore.CYAN + ' | permission = '+attribs[4] + Fore.RESET

            if (not all) and (not attribs[3] or (not 'true' in attribs[3])):
                continue
            else:
                print(display_text)
        print(Style.RESET_ALL)
    
    def print_services(self,all = True):
        display_text = ''
        for attribs in self.services:
            display_text = attribs[1]
            if attribs[2]:
                display_text += Fore.RED + ' | enabled = '+attribs[2]+' |' + Fore.RESET
            if attribs[3]:
                display_text += Fore.GREEN + ' | exported = '+attribs[3]+ Fore.RESET
            if (not all) and (not attribs[3] or (not 'true' in attribs[3])):
                continue
            else:
                print(display_text)
        print(Style.RESET_ALL)
    

    def print_permissions(self):
        display_text = ''
        for permission in self.permissions:
            print("#"*92)
            display_text = Fore.GREEN+'Name:' + Fore.RESET + permission[1]+'\n'
            display_text += Fore.GREEN+'Type:' + Fore.RESET + permission[2]+'\n'
            display_text += Fore.GREEN+'Description:' + Fore.RESET + permission[4]+'\n'
            print(display_text)


    
    def print_database_structure(self):

        res = self.database.query_db("SELECT name FROM sqlite_master WHERE type='table';")

        for entry in res:
            print(Fore.GREEN + "-"*40+"\nTable Name: {}\n".format(entry[0])+"-"*40+Fore.RESET)
        
            columns = self.database.query_db("PRAGMA table_info({});".format(entry[0]))
            print("{c: <25} {t: <15}".format(c="Column Name",t="Type"))
            for column in columns:
                print("{c: <25} {t: <15}".format(c = column[1],t = column[2]))



    def do_patch(self,line):

        text_to_search = "<application" 
        replacement_text ='<application android:debuggable="true" '

        file = line.split(' ')[0]
        if os.path.exists(file):

            try:
                print(GREEN+'[+] Unpacking the apk....'+RESET)
                subprocess.run('java -jar '+ APKTOOL +' d {} -o {}'.format(file,TMP_FOLDER), shell=True)

                print(GREEN+'[+] Extracting the manifest....'+RESET)
                with open(TMP_FOLDER+'/AndroidManifest.xml','rt') as f:
                    data = f.read()

                print(GREEN+'[+] Setting the debug flag to true...')

                if 'android:debuggable="true"' in data:
                    print(RED+"[!] Application is already debuggable !"+RESET)
                else:
                    data = data.replace(text_to_search, replacement_text)
                
                    with open(TMP_FOLDER+'/AndroidManifest.xml','wt') as f:
                        f.write(data)
                    print(GREEN+'[+] Repacking the app...'+RESET)
                    subprocess.run('java -jar '+ APKTOOL +' b {} -o {}'.format(TMP_FOLDER,DEBUGGABLE_APK), shell=True)
                    print(GREEN+'[+] Alligning the apk file.....'+RESET)
                    subprocess.run(ZIPALLIGN +' -p 4 {} {}'.format(DEBUGGABLE_APK,ALLIGNED_APK),shell=True)
                    print(GREEN+'[+] Signing the apk.....'+RESET)
                    subprocess.run(APK_SIGNER +' sign --ks {} -ks-key-alias common --ks-pass pass:password --key-pass pass:password  {}'.format(SIGNATURE, ALLIGNED_APK),shell=True)
                    print(GREEN+'[+] Removing the unsigned apk.....'+RESET)
                    os.remove(DEBUGGABLE_APK)
                    print(GREEN+'[+] Backing up the original...'+RESET)
                    shutil.move(file,'original_'+file)
                    shutil.move(ALLIGNED_APK,file)

                    if ( not Polar('[?] Do you want to keep the extracted resources ?').ask() ):
                        shutil.rmtree(TMP_FOLDER)
            except Exception as e:
                    print(e)
            
        else:
            print("[!] File doesn't exist.")




    def do_query(self,line):
        try:
            print(self.database.query_db(line))
        except Exception as e:
            print(e)
    


    def do_swap(self,line):
        res = self.database.query_db("SELECT sha256, packageName from Application;")
        if res:
            print(Fore.GREEN+"[i] Availlable applications:\n" +Fore.RESET +"-"*7+" "+"-"*70+" "+"-"*57+"\n {0} {1:^68} {2:^60}\n".format("index","sha256","Package Name")+"-"*7+" "+"-"*70+" "+"-"*57)
            index = 0
            for entry in res:
                sha256, package_name = entry
                print(Fore.CYAN+Style.BRIGHT+"{0:^7} {1:^68} {2:^60}".format(index,sha256,package_name))
                index+=1
            
            chosen_index = int(Numeric(Style.RESET_ALL+'\nEnter the index of  application to load:', lbound=0,ubound=index-1).ask())
            chosen_sha256 = res[chosen_index][0]
            self.init_application_info(self.database,chosen_sha256)
        else:
            print(Fore.RED+Style.BRIGHT+ "[!] No Entries found in the given database !"+Style.RESET_ALL)
        return


    def do_cc(self,line):
        subprocess.run('adb -s {} shell {}'.format(self.device.id, line), shell=True)


    def do_show(self,line):
        
        what = line.split(' ')[0]
        if len(line.split(' '))>1:
            flag = line.split(' ')[1]
        else:
            flag = ''
        
        if 'database' in what:
            self.print_database_structure()
        else:
            if self.current_app_sha256 == None:
                print(self.NO_APP_LOADED_MSG)
            else:
                if 'permissions' in what:
                    self.print_permissions()

                elif 'activities' in what:
                    if '-e' in flag:
                        self.print_activities(False)
                    else:
                        self.print_activities()

                elif 'services' in what:
                    if '-e' in flag:
                        self.print_services(False)
                    else:
                        self.print_services()

                elif 'activityAlias' in what:
                    if '-e' in flag:
                        self.print_activity_alias(False)
                    else:
                        self.print_activity_alias()

                elif 'receivers' in what:
                    if '-e' in flag:
                        self.print_receivers(False)
                    else:
                        self.print_receivers()

                elif 'info' in what:
                    self.print_application_info(self.info)
            
                elif 'deeplinks' in what:
                    self.print_deeplinks()
                
                elif 'providers' in what:
                    if '-e' in flag:
                        self.print_providers(False)
                    else:
                        self.print_providers()
                elif 'intentFilters' in what:
                    self.print_intent_filters()
                elif 'manifest' in what:
                    print(self.manifest[0][0].decode('utf-8'))

                elif 'strings' in what:
                    self.print_strings(self.strings)    
                else:
                    print('[i] Usage: show [activities, activityAlias, database, deeplinks, info, intentFilters, manifest, permissions, providers, receivers, services, strings]')




    def complete_show(self, text, line, begidx, endidx):
        if self.current_app_sha256 == None:
            components = ['database']
        else:
            components = sorted(['activityAlias','info','permissions', 'activities', 'services', 'receivers', 'intentFilters','providers', 'deeplinks','strings','database','manifest'])
        if not text:
            completions = components[:]
        else:
            completions = [ f
                            for f in components
                            if f.startswith(text)
                            ]
        return completions


    def do_pull(self, line):
        package = line.split(' ')[0]
        try:
            base_apk = os.popen("adb -s {} shell pm path {} | grep base.apk | cut -d ':' -f 2".format(self.device.id,package)).read()
            print("Extracting: "+base_apk)
            output = os.popen("adb -s {} pull {}".format(self.device.id,base_apk,package)).read()
            print(output)
        except Exception as e:
            print(e)



    def complete_pull(self, text, line, begidx, endidx):
        self.init_packages()
        if not text:
            completions = self.packages[:]
            self.packages = []
        else:
            completions = [ f
                            for f in self.packages
                            if f.startswith(text)
                            ]
            self.packages = []
        return completions
    
    def real_search(self,word,obj):
        found = False
        for module in obj:
            if word.casefold() in module[1].casefold():
                print(module[1].replace(word.casefold(),Fore.GREEN + word.casefold()+Fore.RESET))
                found = True
        return found
      

    def do_search(self, line):

        if self.current_app_sha256 == None:
            print(self.NO_APP_LOADED_MSG)
        else:
            try:
                what = line.split(' ')[0]
                print(RED+'Searching Activities:'+RESET)
                if not self.real_search(what, self.activities):
                    print('No Activities found containing: {} !'.format(what))
                
                print(RED+'Searching Services:'+RESET)
                if not self.real_search(what, self.services):
                    print('No Services found containing: {} !'.format(what))            

                print(RED+'Searching Receivers:'+RESET)
                if not self.real_search(what, self.receivers):
                    print('No Receivers found containing: {} !'.format(what)) 

                print(RED+'Searching Providers:'+RESET)
                if not self.real_search(what, self.providers):
                    print('No Providers found containing: {} !'.format(what)) 

                print(RED+'Searching String Resources:'+RESET)

                found = False
                for line in self.strings.split('\n'):
                    if what.casefold() in  line:
                        print(line.replace(what.casefold(),Fore.GREEN + what.casefold()+Fore.RESET))
                        found = True
                if not found:
                    print('No Strings found containing: {} !'.format(what))

            except Exception as e:
                print(e)


    def real_import(self,apk_file):
        try:
            self.guava.full_analysis(apk_file)
            self.init_application_info(self.database,self.guava.sha256sum(apk_file))
        except Exception as e:
            print(e)
        
    def do_import(self,line):
        apkfile = line.split(' ')[0]
        if os.path.exists(apkfile):
            self.real_import(apkfile)
        else:
            print(Fore.RED+"[!] Fatal: can't find: {} ".format(apkfile)+Fore.RESET)


    def do_notify(self,line):
        try:
            self.init_packages()   
            if 'com.medusa.agent' in self.packages:   
                output=os.popen("adb -s {} shell am broadcast  -a com.medusa.NOTIFY --es subject {} --es body {}".format(self.device.id,line.split(' ')[0],line.split(' ')[1])).read()
                print(output)
            else:
                print("[!] Medusa Agent must be installed and running on the device, type 'installagent' to install it.")
        except Exception as e:
            print(e)
            

    def init_packages(self):
        for line1 in os.popen('adb -s {} shell pm list packages -3'.format(self.device.id)):
            self.packages.append(line1.split(':')[1].strip('\n'))
   
    def do_uninstall(self,package):
        try:         
            output=os.popen("adb -s {} uninstall {}".format(self.device.id,package.split(' ')[0])).read()
            print(output)
        except Exception as e:
            print(e)
            

    def do_kill(self,package):
        try:         
            print(package)
            output=os.popen("adb -s {} shell  am force-stop {}".format(self.device.id,package.split(' ')[0])).read()
            print(output)
        except Exception as e:
            print(e)
            

    def do_spawn(self,package):
        try:         
            print('[+] Starting {}'.format(package))
            os.popen("adb -s {} shell  monkey -p {} -c 'android.intent.category.LAUNCHER 1'".format(self.device.id,package.split(' ')[0])).read()
            print('[+] {} started'.format(package))
        except Exception as e:
            print(e)
            

    def complete_spawn(self, text, line, begidx, endidx):

        self.init_packages()
        if not text:
            completions = self.packages[:]
            self.packages = []
        else:
            completions = [ f
                            for f in self.packages
                            if f.startswith(text)
                            ]
            self.packages = []
        return completions

    def complete_kill(self, text, line, begidx, endidx):

        self.init_packages()
        if not text:
            completions = self.packages[:]
            self.packages = []
        else:
            completions = [ f
                            for f in self.packages
                            if f.startswith(text)
                            ]
            self.packages = []
        return completions

    def complete_uninstall(self, text, line, begidx, endidx):

        self.init_packages()
        if not text:
            completions = self.packages[:]
            self.packages = []
        else:
            completions = [ f
                            for f in self.packages
                            if f.startswith(text)
                            ]
            self.packages = []
        return completions



    def do_adb(self,line,cmd=None,frombs=False):
        
        if cmd == None:
            print("[i] Type 'exit' to return ") 
            cmd =  input(GREEN+'{}:adb:'.format(self.device.id)+RESET)

        while cmd != 'exit':  
            if cmd != 'exit':
                subprocess.run('adb -s {} {}'.format(self.device.id,cmd), shell=True)
                if frombs == True:
                    return
            cmd = input(GREEN+'{}:adb:'.format(self.device.id)+RESET)

    def do_install(self,line):
        try:
            if len(line.split(' ')):
                apk_file = line.split(' ')[0]

                if os.path.exists(apk_file):
                    self.do_adb('adb','install {}'.format(apk_file),True)
        except Exception as e:
            print(e)


    def do_installagent(self,line):
        try:
            subprocess.run('adb -s {} install -g {}'.format(self.device.id,os.path.join(self.base_directory,'../dependencies/agent.apk')),shell=True)
        except Exception as e:
            print(e)


    def do_trace(self,line):
        if self.current_app_sha256 == None:
            print(self.NO_APP_LOADED_MSG)
        else:
            try:
            
                opsys = platform.system()
                script = self.create_script(opsys,line)
                path = os.getcwd()

                if not 'Error' in script:
                    if 'Darwin' in opsys:
                        subprocess.run("""osascript -e 'tell application "Terminal" to do script "{}" ' """.format(path+script), shell=True)
                    elif 'Linux' in opsys:
                        subprocess.run("""x-terminal-emulator -e {}""".format(path+script)) 
                    elif 'Windows' in opsys:
                        subprocess.call('start /wait {}'.format(path+script), shell=True)
            except Exception as e:
                print(e)


    def create_script(self,opsys,line):

        switch = line.split(' ')[0].strip()
        valid = True

        if '-j' in switch:
            param1 = line.split(' ')[1]+ '*!*'
            param = """frida-trace -D {} {} -j '{}' """.format(self.device.id,self.info[0][2],param1)
        elif '-n' in switch:
            param1 = line.split(' ')[1]+ '*'
            param = """frida-trace -D {} -i '{}' {}""".format(self.device.id,param1,self.info[0][2])
        elif '-a' in switch:
            param1 = line.split(' ')[1].strip()
            param = """frida-trace -D {} -I '{}' {}""".format(self.device.id,param1,self.info[0][2])
        else:
            print('[E] Invalid command, run help for options!')  
            valid = False        

        if valid:
            path = os.getcwd()

            if 'Windows' in opsys:
                script = path + '/script.bat'
                with open(script,'w') as file:
                    file.write(param) 
            else:
                script = path + '/script.sh'
                with open(script,'w') as file:
                    file.write(param) 
                os.chmod(script, 0o775)
        else:
            script = 'Error'

        return script


    def print_proxy(self):
        
        settings = os.popen("adb -s {} shell settings get global http_proxy".format(self.device.id)).read()
        print (WHITE+"--------------Global proxy settings-----------------:"+RESET)
        print ('Current proxy: {}'.format(settings))
        print (WHITE+"--------------IP tables settings--------------------:"+RESET)
        output = subprocess.run("adb -s {} shell iptables -t nat -L".format(self.device.id), shell=True)
        print(output)
 

    def do_screencap(self, line):
        try:
            if '-o' in line.split(' ')[0]:
                os.popen("adb -s {} exec-out screencap -p > {}".format(self.device.id,line.split(' ')[1]))
                print('[!] Screencap saved successfully to {}'.format(line.split(' ')[1]))
            else:
                print('[!] Usage: screencap -o filename.png')
        except Exception as e:
            print(e)
            print('[!] Usage: screencap -o filename.png')



    def do_type(self,line):

        print("Type 'exit' to quit")

        while 'exit' not in line:
            line = input(':')
            os.popen("adb -s {} shell input text {}".format(self.device.id,line))



    def do_clear(self,line):
        os.system('clear')


    def do_c(self, line):
        subprocess.run(line, shell=True)


    def do_proxy(self,line):

        command = line.split(' ')[0]
        try:
            if 'get' in command:
                self.print_proxy()
            elif 'reset' in command:
                os.popen("adb -s {} shell settings put global http_proxy :0".format(self.device.id))  
                os.popen("adb -s {} shell iptables -t nat -F".format(self.device.id))
                time.sleep(2) 
                self.print_proxy()
            elif 'set' in command:
                switch = ip = line.split(' ')[1].split(':')[0]
                if '-t' in switch:
                    ip = line.split(' ')[2].split(':')[0]
                    port = line.split(' ')[2].split(':')[1]
                    self.transproxy(ip,port)
                else:
                    ip = line.split(' ')[1].split(':')[0]
                    port = line.split(' ')[1].split(':')[1]
                    os.popen("adb -s {} shell settings put global http_proxy {}:{}".format(self.device.id,ip,port)) 
                    time.sleep(2) 
                    self.print_proxy()
            else:
                print('[!] Usage: proxy [set,get,reset] [<ip>:<port>] [-t]')
        except Exception as e:
            print(e)


    def complete_proxy(self, text, line, begidx, endidx):
        proxy_cmd = ['set','get','reset']
        if not text:
            completions = proxy_cmd[:]
        else:
            completions = [ f
                            for f in proxy_cmd
                            if f.startswith(text)
                            ]
        return completions


    def transproxy(self,ip,port):
        trasnproxy_path = os.path.join(self.base_directory,'../utils/transproxy.sh')
        try:
            print('[i] Pushing transproxy script !')
            os.popen("adb -s {} push {} /data/local/tmp/transproxy.sh".format(self.device.id,trasnproxy_path)).read() 
            print('[i] Executing script')
            os.popen("adb -s {} shell 'chmod +x /data/local/tmp/transproxy.sh; /data/local/tmp/transproxy.sh {} {}; rm /data/local/tmp/transproxy.sh'".format(self.device.id,ip,port)).read()
            self.print_proxy()
        except Exception as e:
            print(e)




    def do_installBurpCert(self,line):
        install_script = os.path.join(self.base_directory,'../utils/installBurpCert.sh')
        self.init_packages()
        if 'com.medusa.agent' not in self.packages:
            print("[!] Medusa Agent must be installed and running on the device, type 'installagent' to install it.")
            return
        try:
            a = ''
            while a != 'y' and a !='x':
                a = input("""[!] Make sure that burp is running on 127.0.0.1:8080\n\nType 'y' to continue or 'x' to cancel:""")

            if a == 'y':
                os.popen("chmod +x {}; {} {}".format(install_script,install_script,self.device.id)).read()
                os.popen("adb -s {} shell am broadcast -a com.medusa.INSTALL_CERTIFICATE -n com.medusa.agent/.Receiver".format(self.device.id)).read()

                time.sleep(1)
                print(GREEN+"""
-------------------------------------------------------------------
Note: Burp certificate has been copied to sdcard, use the following 
commands to install it as a system certificate:
-------------------------------------------------------------------
$adb remount
$cd /system/etc/security/cacerts
$mkdir tmp
$mv * tmp/
$mv /sdcard/*.der /system/etc/security/cacerts/*.0
                """+RESET)
                print()
        except Exception as e:
            print('')
        


    def do_jdwp(self,line):
        try:
            pid = os.popen("adb -s {} shell pidof {}".format(self.device.id,line.split(' ')[0])).read()
            output = os.popen("adb -s {} forward tcp:6667 jdwp:{}".format(self.device.id,pid)).read()
            print(output)
            
            subprocess.run('jdb -attach localhost:6667', shell=True)

        except Exception as e:
            print(e)
            print('[!] Usage: jdwp package_name')



    def complete_jdwp(self, text, line, begidx, endidx):

        self.init_packages()
        if not text:
            completions = self.packages[:]
            self.packages = []
        else:
            completions = [ f
                            for f in self.packages
                            if f.startswith(text)
                            ]
            self.packages = []
        return completions


    def do_start(self,line):
        if self.current_app_sha256 == None:
            print(self.NO_APP_LOADED_MSG)
        else:
            try:
                cmd = "adb -s {} shell 'am start -n {}/{}'".format(self.device.id,self.info[0][2],line.split(' ')[0])
                print("adb command: {}".format(cmd))
                output=os.popen(cmd).read()
                print(output)
            except Exception as e:
                print(e)
            


    def complete_start(self, text, line, begidx, endidx):

        if not text:
            completions = self.activity_names[:]
        else:
            completions = [ f
                            for f in self.activity_names
                            if f.startswith(text)
                            ]
        return completions



    def do_startsrv(self,line):
        if self.current_app_sha256 == None:
            print(self.NO_APP_LOADED_MSG)
        else:
            cmd = "adb -s {} shell 'am startservice -n {}/{}'".format(self.device.id,self.info[0][2],line.split(' ')[0])
            print("adb command: {}".format(cmd))
            try:         
                output=os.popen(cmd).read()
                print(output)
            except Exception as e:
                print(e)
            

    def complete_startsrv(self, text, line, begidx, endidx):
        if not text:
            completions = self.service_names[:]
        else:
            completions = [ f
                            for f in self.service_names
                            if f.startswith(text)
                            ]
        return completions

    def do_stopsrv(self,line):
        if self.current_app_sha256 == None:
            print(self.NO_APP_LOADED_MSG)
        else:
            try:         
                output=os.popen("adb -s {} shell 'am stopservice -n {}/{}'".format(self.device.id,self.info[0][2],line.split(' ')[0])).read()
                print(output)
            except Exception as e:
                print(e)
                

    def complete_stopsrv(self, text, line, begidx, endidx):
        if not text:
            completions = self.services[:]
        else:
            completions = [ f
                            for f in self.services
                            if f.startswith(text)
                            ]
        return completions


    def do_deeplink(self,line):
        if self.current_app_sha256 == None:
            print(self.NO_APP_LOADED_MSG)
        else:
            try:
                if len(line.split()) > 1 and '--poc' in line.split()[1]:
                    print("[+] Creating POC")
                    poc = '<head></head>'+'<body>'+'<a href="'+line.split()[0]+'">DEEPLINK POC</a></body></html>'
                    f = open("poc.html",'w')
                    f.write(poc)
                    f.close()
                    print("[+] POC created")

                else:
                    output=os.popen("adb -s {} shell am start -W -a android.intent.action.VIEW -d {}".format(self.device.id,line.split(' ')[0])).read()
                    print(output)
            except Exception as e:
                print(e)

    def complete_deeplink(self, text, line, begidx, endidx):
        s = list(self.schemes)
        h = list(self.hosts)


        if not text:
            completions = s[:]
        else:
            if not ':' in text:
                completions = [ f
                                for f in s
                                if f.startswith(text)
                                ]
            else:
                w = text.split(':')[1]
                completions = [ f
                                for f in h
                                if f.startswith(w)
                                ]
        return completions



    def run_command(self,cmd):
        proccess = subprocess.Popen(cmd,stdout = subprocess.PIPE,stderr=subprocess.PIPE)
        output, error = proccess.communicate()
        if proccess.returncode != 0:
            return error
        else:
            return output


    def do_box(self,line):

        arch = self.run_command(["adb","-s",'{}'.format(self.device.id),"shell","getprop","ro.product.cpu.abi"])

        if b'v8' in arch:
            binary = "busybox-armv8l"
        elif 'v7' in arch:
            binary = "busybox-armv7l"
        else:
            print("Arch is not supported !")
            return

        output = self.run_command("adb -s {} shell ls /data/local/tmp/{}".format(self.device.id,binary).split())
        if b'No such file' in output:
            download = Polar("[!] Can't find Bussybox in this device, do you want to download it ?").ask()
            if download:
                try:
                    print("[i] Attempting to download the file using 'curl' .....")
                    print(self.run_command(["curl", BUSSY_BOX_URL+binary, "--output", "busybox.tmp"]).decode('utf-8'))
                    if os.path.exists("./busybox.tmp"):
                        print("[i] Download successfull, pushing the binary to the device as '/data/local/tmp/{}'".format(binary))
                        print(self.run_command(["adb", "-s", "{}".format(self.device.id), "push", "./busybox.tmp", "/data/local/tmp/{}".format(binary)]).decode('utf-8'))
                        print("[i] Deleting local file...")
                        print(self.run_command(["rm", "./busybox.tmp"]).decode('utf-8'))
                        print(self.run_command(["adb", "-s", "{}".format(self.device.id), "shell", "chmod", "+x", "/data/local/tmp/{}".format(binary)]).decode('utf-8'))
                        print("[i] Setting the aliases file...")
                        shellfile = os.path.abspath(os.path.join(self.base_directory,'../utils/busybox.sh'))
                        with open(shellfile,'r') as sf:
                            data = sf.read()
                        data = data.replace('to_be_replaced',binary)
                        with open(shellfile,'w') as sf:
                            sf.write(data)
                        subprocess.run("""adb -s {} push {} /data/local/tmp/busybox.sh""".format(self.device.id,shellfile),shell=True)
                    else:
                        print("[!] Download Failed !")
                        return
                except Exception as e:
                        print(e)
            else:
                return
        print("[i] Busybox support has already been installed.\n[i] Type: source /data/local/tmp/busybox.sh")
        self.do_adb("adb","shell",True)
            

    def do_exit(self,line):
        print('[i] Checking the working directory for leftovers... ')
        try:
            if os.path.isfile('./script.sh'):
                Polar('\tDo you want to delete the trace script file ?',
                    lambda: os.remove('./script.sh')).ask()
            if os.path.isfile('./script.bat'):
                Polar('\tDo you want to delete the trace script file?',
                    lambda: os.remove('./script.bat')).ask()
            if os.path.exists("__handlers__/"):
                Polar('\tDo you want to delete the __handlers__ folder?',
                    lambda: os.system("rm -r __handlers__/")).ask()



        except Exception as e:
            print(e) 

        print('All good...Bye !!')
        exit()


    def highlight(self,word,str):
        if word.casefold() in str.casefold():
                return str.replace(word.casefold(),Back.WHITE + Style.BRIGHT+Fore.BLACK + word.casefold()+Style.RESET_ALL)
        else:
            return ''


    def do_help(self,line):
        if len(line.split(' ')) > 0:
            topic = line.split(' ')[0]
            h = self.highlight(topic, HELP_MESSAGE)
            if h == '':
                print("[i] No help availlable for '{}'".format(topic))
            else:
                print(h)
        else:
            print(HELP_MESSAGE)
    