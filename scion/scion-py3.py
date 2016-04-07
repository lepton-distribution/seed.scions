#!/usr/bin/python

import os
import subprocess
import sys
import errno
import argparse
import re
import shutil

from os.path import expanduser
from collections import OrderedDict
from urllib.parse import urlparse

#import jaraco.windows.filesystem as fs; fs.patch_os_module()
#import jaraco.windows.filesystem as fs


####################################################################
# scion const definitions
####################################################################
# scion definition
#environment variable: active root stock SCION_ROOTSTOCK
ENV_VAR_ACTIVE_ROOTSTOCK ="SCION_ROOTSTOCK" 
#
default_shelf_path="."
#
scion_stem_dir="scion"
#
scion_hidden_dir=".scion"

# ~/.scion.settings/
scion_settings_dir=".scion.settings"

# ~/.scion.settings/.scion.rootstock.active
scion_rootstock_active_file=".scion.rootstock.active"

# ~/.scion.settings/.scion.projects.list
scion_projects_list_file=".scion.projects.list"

# $SCION_ROOTSTOCK/depots/
rootstock_depots_dir="depots"

# $SCION_ROOTSTOCK/tauon/
rootstock_trunk_dir="tauon"

# $SCION_ROOTSTOCK/depots/lepton
lepton_shelf_dir="lepton"
# $SCION_ROOTSTOCK/depots/lepton/building/
building_scion_dir="building"

# seed. shelf lepton.  $SCION_ROOTSTOCK/depots/lepton
# seed. shelf lepton, scion root  $SCION_ROOTSTOCK/depots/lepton/root
seed_lepton_root_path="lepton/root"

# $SCION_ROOTSTOCK/depots/ ... scion local location ... /scion/.scion/.scion.sources.list 
scion_sources_list_file=".scion.sources.list"

# $SCION_ROOTSTOCK/depots/ ... scion local location ... /scion/.scion/.scion.ramification 
scion_ramification_file=".scion.ramifications"

# $SCION_ROOTSTOCK/tauon/.scion.grafted.list
scion_grafted_list_file=".scion.grafted.list"


# .../src/, -/build/[scion name]/,    
src_dir="src"
build_dir="build"

# predified tree nodes:  kernel, net, fs, core ...
#kernel
kernel_dir="kernel"
core_dir="core"
dev_dir="dev"
fs_dir="fs"
net_dir="net"

kernel_core_path=kernel_dir+"/"+core_dir
kernel_dev_path=kernel_dir+"/"+dev_dir
kernel_fs_path=kernel_dir+"/"+fs_dir
kernel_net_path=kernel_dir+"/"+net_dir

# lib
lib_dir="lib"

# usr
usr_dir="usr"
sbin_dir="sbin"
bin_dir="bin"
usr_sbin_path = usr_dir+"/"+sbin_dir
usr_bin_path = usr_dir+"/"+bin_dir 

# version 0.1.0.2
# command 
#
# scion.py seeding --version [master|v.0.1.0.1] https://github.com/lepton-distribution/lepton-seed.scions.git [optional path to .scion directory default scion/.scion]
#    - get ramification and source list
#    - clone all depot specifyed in ramification
#    - grafted list is updated
# 
# scion.py update
#     - update all depot specified in grafted list 
#    
# scion.py install
# 
# active rootstock  path is a container
#
# scion install c:/my/root/stock/path
#     update in $HOME/.scion.settings/.scion.rootstock.active
#
# scion rootstock c:/my/root/stock/path
#   update in $HOME/.scion.settings/.scion.rootstock.active
#
# scion seed  --developer --version --force [shelf@scion::name|*-version|*]  https://url/my/depot.git  path/to/scion/.scion 
#   --developper "git clone" command does not use --single-branch, but version master and checkout branch|version from .scion-ramification 
#
# 
# scion graft-update 
# - full update grafted seeds (update seeds):  take into account ramification or source liste change. regenerate  
#   1: ungraft all
#   2: get all seeds in in grafted list
#   3: get .scion of each seed in grafted list
#   4: update each seeds in grafted list
#   5: update (or clone new scion) all scion in each seed 
#   6: update grafted list
#   7: graft all
#     
#
#  - lite update only current scions
# scion graft-refresh  
#  1: get all scions in grafted list
#  2: update scion with his associated .scion  
#
# scion graft-add [shelf@scion::name]  [local path] 
# scion graft-remove [shelf@scion::name]  [local path] 
# scion graft-replace --from [shelf@scion::name] --to [shelf@scion::name] [local path] 
# scion graft-clean
#   - ungraft all scions
#   - remove grafted list file.

####################################################################
# scion global var definitions
####################################################################
# scion source list 
scions_sources_list = list()
# scion ramification 
scions_list = list()
# scion grafted list 
scions_grafted_dictionary = OrderedDict()
# seeds grafted list 
seeds_grafted_dictionnary = OrderedDict()


####################################################################
# windows os.symlink() work around. os.symlink not inplemented.
####################################################################
if os.name == "nt":
    def symlink_ms(source, link_name):
        import ctypes
        #
        csl = ctypes.windll.kernel32.CreateSymbolicLinkW
        csl.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        csl.restype = ctypes.c_ubyte
        flags = 1 if os.path.isdir(source) else 0
        try:
           if csl(link_name, source.replace('/', '\\'), flags) == 0:
              raise ctypes.WinError()
        except:
           print("win symlink: exception: pass")
           pass
    os.symlink = symlink_ms

####################################################################
# scion utils functions
####################################################################
# compare version
# print(compare('1.0', 'beta13'))    
# print(compare('1.1.2', '1.1.2'))
# print(compare('1.2.2', '1.1.2'))
# print(compare('1.1.beta1', '1.1.beta2'))
def _preprocess(v, separator, ignorecase):
    if ignorecase: v = v.lower()
    return [int(x) if x.isdigit() else [int(y) if y.isdigit() else y for y in re.findall("\d+|[a-zA-Z]+", x)] for x in v.split(separator)]

#
def compare(a, b, separator = '.', ignorecase = True):
    a = _preprocess(a, separator, ignorecase)
    b = _preprocess(b, separator, ignorecase)
    try:
        return (a > b) - (a < b)
    except:
        return False
#
def grow_branch(path):
   dir = os.path.dirname(path+"/")
   if not os.path.exists(dir):
      os.makedirs(dir)
      print("new branch\n", dir)

#  
def grow_tree(arg_install_path,arg_tree):
   for path in arg_tree :
       full_path=arg_install_path+"/"+path
       grow_branch(full_path)

#
def get_current_scion_path():
  #current_path = os.path.realpath(sys.argv[0]).rsplit("/")
  current_path = os.path.realpath(os.getcwd()).replace("\\","/").rsplit("/")
  #
  print ("current scion path: " , current_path)
  #
  scion_path=list()
  for dir in current_path:
    scion_path.append(dir)
    if dir==scion_stem_dir:
      return "/".join(scion_path)
  return ""


####################################################################
# rootstock functions ~/.scion.settings/.scion.rootstock.active
####################################################################
#
def extract_active_rootsock_path(line): 
   active_rootsock_label = line.split(" ")[0]
   active_rootsock_path = line.split(" ")[1]
   return  active_rootsock_path

#
def build_active_rootsock_path(active_rootsock_path):
   active_rootsock_label=ENV_VAR_ACTIVE_ROOTSTOCK
   line = active_rootsock_label + " "+ active_rootsock_path
   return line

#
def get_active_rootstock_path(rootstock_active_file_path):
   try:
      with open(rootstock_active_file_path,"r") as f:
         entry_index=0
         for line in f:
            entry = re.sub('[ \t\n]+' , ' ', line)
            # exclude comment line
            entry=entry.split("#",1)[0]
            #
            if(len(entry)<=0):
               continue
            try:
               active_rootsock_path = extract_active_rootsock_path(entry)
               print ("active rootstock path: ", entry)
               return active_rootsock_path
            except IndexError:
              continue
            #
   except IOError:
      print ("warning file ", rootstock_active_file_path, " not exist\n") 
   return ""

#
def inventory_active_rootstock_path(current_path):
  dirs = os.listdir(current_path)
  for entry_name in dirs:
    if os.path.isdir(current_path+"/"+entry_name):
      #find scion signature  scion/.scion/
      if not os.path.exists(current_path+"/"+entry_name+"/"+scion_stem_dir+"/"+scion_hidden_dir):
        inventory_active_rootstock_path(current_path+"/"+entry_name)
      else :
        print ("found scion path: ", (current_path+"/"+entry_name))

#
def set_active_rootstock_path(rootstock_active_file_path,active_rootsock_path):
   with open(rootstock_active_file_path,"a+") as f:
      entry  = build_active_rootsock_path(active_rootsock_path)
      f.truncate(0)
      f.write(entry)
      print ("active rootstock path: ", entry)


####################################################################
# scion ramification functions ..../scion/.scion/.scion.ramification
# list of: shelf scion version
####################################################################
def extract_scion_entry(line): 
   shelf = line.split(" ")[0]
   scion = line.split(" ")[1]
   version = line.split(" ")[2]
   print ("extract_scion_entry: ",shelf, " ", " ",scion," ",version)
   return  shelf, scion, version

def read_ramification(file_path):
   try:
      with open(file_path,"r") as f:
         entry_index=0
         for line in f:
            entry = re.sub('[ \t\n]+' , ' ', line)
            # exclude comment line
            entry=entry.split("#",1)[0]
            #
            if(len(entry)<=0):
               continue
            try:
               shelf, scion, version = extract_scion_entry(entry)
            except IndexError:
              continue

            scions_list.append(entry)
            print ("entry[", entry_index, "]: " ,entry)
            entry_index=entry_index+1
   except IOError:
      print ("error file ", file_path," not exist\n" ) 

def write_ramification(file_path,entry):
   with open(file_path,"a+") as f:
      entry = re.sub('[ \t]+' , ' ', entry)
      read_ramification(file_path)
      scions_list.append(entry)
      f.truncate(0)
      f.write("\n".join(scions_list))
      print ("-> entry: " , entry ," added") 
 
def remove_ramification(file_path,entry_index):
   with open(file_path,"a+") as f:
      read_ramification(file_path)
      entry = scions_list.pop(entry_index)
      f.truncate(0)
      f.write("\n".join(scions_list))
      print ("<- entry: ", entry, " removed" )


####################################################################
# scion location (git url, local path) functions .../scion/.scion/.scion.sources.list 
# list of: shelf scion version location  (git url, local path)
####################################################################
def extract_source_entry(line): 
   shelf = line.split(" ")[0]
   scion = line.split(" ")[1]
   version = line.split(" ")[2]
   location = line.split(" ")[3]
   try:
    path = line.split(" ")[4] # optional scion path in repository
   except IndexError:
    path = ""
   #print "extract_scion_location: %s %s %s %s %s\n" %(shelf,scion,version,location,path)
   return  shelf, scion, version, location , path

def get_scion_location(sources_list_file_path,shelf,scion,version):
   try:
      url_selected=""
      version_selected=""
      location_selected=""
      path_selected=""
      with open(sources_list_file_path,"r") as f:
         entry_index=0
         for line in f:
            entry = re.sub('[ \t\n]+' , ' ', line)
            # exclude comment line
            entry=entry.split("#",1)[0]
            #
            if(len(entry)==0):
              continue
            #
            scions_sources_list.append(entry)
            #
            try:
              shelf_ex, scion_ex, version_ex, location_ex, path_ex = extract_source_entry(entry)
            except IndexError:
              continue
            #
            if shelf==shelf_ex and scion==scion_ex :
              if version!="?" and version==version_ex :
               version_selected=version_ex
               location_selected=location_ex
               path_selected=path_ex
               break
              else:
                if(compare(version_ex, version_selected)>0):
                  version_selected=version_ex
                  location_selected=location_ex
                  path_selected=path_ex
            #
            entry_index=entry_index+1
      print ("found location of scion ", scion," (version ", version_selected, ") on shelf ", shelf, " from ", location_selected, " \n")
      return location_selected, path_selected
   except IOError:
      print ("warrning file ", sources_list_file_path, " not exist\n")


####################################################################
# scion graft preparation functions. 
# read scions list in .scion.ramification, find location in .scion.sources.list 
# and generate ($SCION_ROOTSTOCK/tauon/.scion.grafted.list)
####################################################################
#added scion in scion graft list files
def extract_scions_grafted_entry(line): 
   shelf = line.split(" ")[0]
   scion = line.split(" ")[1]
   version = line.split(" ")[2] 
   location = line.split(" ")[3] # repository local location with scion path
   #
   try:
    seed_dot_scion_path = line.split(" ")[4] # seed .scion path in repository
   except IndexError:
    seed_dot_scion_path = ""
   #
   return  shelf, scion, version, location, seed_dot_scion_path

#
def scions_grafted_cache(rootstock_path):
   #
   scion_grafted_list_file_path=rootstock_path+"/"+rootstock_trunk_dir+"/"+scion_grafted_list_file
   #
   try:
      with open(scion_grafted_list_file_path,"r") as f:
         entry_index=0
         for line in f:
            entry = re.sub('[ \t\n]+' , ' ', line)
            # exclude comment line
            entry=entry.split("#",1)[0]
            #
            if(len(entry)<=0):
               continue
            #
            try:
               shelf, scion, version, location, seed_dot_scion_path = extract_scions_grafted_entry(entry)
            except IndexError:
              continue
            entry_key = shelf+"/"+scion
            #
            scions_grafted_dictionary[entry_key] = entry
            #
            print ("dictionary[",entry_key,"]:", entry )
            entry_index=entry_index+1
   except IOError:
      print ("warning file ", scion_grafted_list_file_path, " not exist\n")

#
def scions_grafted_update(rootstock_path):
   #
   scion_grafted_list_file_path=rootstock_path+"/"+rootstock_trunk_dir+"/"+scion_grafted_list_file
   #
   with open(scion_grafted_list_file_path,"a+") as f:
      f.truncate(0)
      for entry in scions_grafted_dictionary.values():
         f.write(entry+"\n")

#
def scions_grafted_clean(rootstock_path):
   #
   scion_grafted_list_file_path=rootstock_path+"/"+rootstock_trunk_dir+"/"+scion_grafted_list_file
   #
   try:
      os.remove(scion_grafted_list_file_path)
      print ("file ", scion_grafted_list_file_path, " is removed\n")
   except OSError:
      print ("error: file ", scion_grafted_list_file_path, " cannot be removed\n")

      
####################################################################
# git repositry management download, update 
####################################################################
def scion_graft_git_update(entry_key,sources_list_file_path,rootstock_path,shelf,scion,version):
   # entry does not exists: new entry.
   # find scion location
   location_url, path = get_scion_location(sources_list_file_path,shelf,scion,version)
   # local or distant location
   parsed_location_url=urlparse(location_url)
   # local or url
   if len(parsed_location_url.scheme)>0:
      # if distant check if already downloaded
      prefix_scion_name = scion.split("::")[0] #scion name [prefix root-scion-name]['.' suffix sub-scion-name]
      local_scion_depot_path=rootstock_path+"/"+rootstock_depots_dir+"/"+shelf+"/"+prefix_scion_name+"/"+version
      #check if local git depot exists
      if os.path.exists(local_scion_depot_path+"/.git"):
      	# git pull
        git_command="git pull"
        # execute git command
        try:
        	retcode = subprocess.check_call(git_command, shell=True, cwd = local_scion_depot_path)
        	if retcode < 0:
        		print("error: ", git_command," : ", -retcode, file=sys.stderr)
        	else:
        		print("scions from depot ", location_url ," update succeed: ", retcode, file=sys.stderr)
        except subprocess.CalledProcessError as e:
        	print("error: execution failed:", e, file=sys.stderr)

#
def scion_graft_git_clone(entry_key,seed_dot_scion_path,sources_list_file_path,rootstock_path,shelf,scion,version):
   # entry does not exists: new entry.
   #find scion location
   location_url, path = get_scion_location(sources_list_file_path,shelf,scion,version)
   # local or distant location
   parsed_location_url=urlparse(location_url)
   #
   if len(parsed_location_url.scheme)>0:
      # if distant check if already downloaded
      prefix_scion_name = scion.split("::")[0] #scion name [prefix root-scion-name]['.' suffix sub-scion-name]
      local_scion_depot_path=rootstock_path+"/"+rootstock_depots_dir+"/"+shelf+"/"+prefix_scion_name+"/"+version
      #check if local git depot exists
      if not os.path.exists(local_scion_depot_path+"/.git"):
         # git clone -b v-0.0.0.1 --single-branch git://ks354041.kimsufi.com/scion-shelves/lepton-kernel.scion.git ./lepton/kernel/v-0.0.0.1
         git_command="git clone -b "+version+" --single-branch "+location_url+" "+local_scion_depot_path
         # execute git command
         os.system(git_command)
         if not os.path.exists(local_scion_depot_path+"/.git"):
            sys.exit("error: cannot download : "+location_url)
      # create new entry
      entry =shelf+" "+scion+" "+ version+" "+local_scion_depot_path
      # add scion path in repository
      if(len(path)>0):
        entry=entry+"/"+path
      #add seed .scion path
      entry = entry+' '+seed_dot_scion_path 
      # add entry
      scions_grafted_dictionary[entry_key]=entry 

   else:
      # location_url is a local location 
      #
      entry = shelf+" "+scion+" "+ version+" "+location_url
      if(len(path)>0):
        entry=entry+"/"+path
      #add seed .scion path
      entry = entry+' '+seed_dot_scion_path 
      # add entry
      scions_grafted_dictionary[entry_key]=entry 
   
#
def scion_graft_scions_update(seed_dot_scion_path,sources_list_file_path,rootstock_path):
   #
   read_ramification(seed_dot_scion_path+'/'+scion_ramification_file)
   #
   scions_grafted_cache(rootstock_path)
   #
   for entry in scions_list:
      try:
         shelf,scion,version = extract_scion_entry(entry)
      except IndexError:
         sys.exit("error: not valid entry: "+entry+"\n")
      #is already exist in scion grafted list
      entry_key = shelf+"/"+scion
      #
      if entry_key in scions_grafted_dictionary:
         line = scions_grafted_dictionary[entry_key]
         # entry already exists
         try:
            shelf_grafted, scion_grafted, version_grafted, location_grafted, seed_dot_scion_path_grafted = extract_scions_grafted_entry(line)
         except IndexError:
            print ("error : missing parameters in line", line, "\n")
            exit(0)

         if(compare(version,version_grafted)>0):
            print ("information: scions ", scion, " version ", version, " from shelf " ,shelf ," will be installed instead current version ", version_grafted)
            #ask which version will be used
            #if used new scion version from ramification file instead version from grafted files then download it.
         elif (compare(version,version_grafted)<0):
            #nothing to do
            print ("information: scions ", scion, " version ", version, " from shelf " ,shelf," : current version ", version_grafted," is more recent.") 
         else:
          print ("information: scions ", scion, " version ", version, " from shelf " ,shelf," is existing in depots. Updating...\n")
          scion_graft_git_update(entry_key,sources_list_file_path,rootstock_path,shelf,scion,version)
          print ("information: scions ", scion, " version ", version, " from shelf " ,shelf," Updated\n")
      else:
        scion_graft_git_clone(entry_key,seed_dot_scion_path,sources_list_file_path,rootstock_path,shelf,scion,version)
        
      #end try except
   #end for
   scions_grafted_update(rootstock_path)
#

def scion_graft_scions_clone(seed_dot_scion_path,sources_list_file_path,rootstock_path):
   #
   read_ramification(seed_dot_scion_path+'/'+scion_ramification_file)
   #
   scions_grafted_cache(rootstock_path)
   #
   for entry in scions_list:
      try:
         shelf,scion,version = extract_scion_entry(entry)
      except IndexError:
         sys.exit("error: not valid entry: "+entry+"\n")
      #is already exist in scion grafted list
      entry_key = shelf+"/"+scion
      #
      if entry_key in scions_grafted_dictionary:
         line = scions_grafted_dictionary[entry_key]
         # entry already exists
         try:
            shelf_grafted, scion_grafted, version_grafted, location_grafted, seed_dot_scion_path_grafted = extract_scions_grafted_entry(line)
         except IndexError:
            print ("error : missing parameters in grafted entry line", line, "\n")

         if(compare(version,version_grafted)>0):
            print ("information: scions ", scion, " version ", version, " from shelf " ,shelf ," will be installed instead current version ", version_grafted)
            #ask which version will be used
            #if used new scion version from ramification file instead version from grafted files then download it.
         elif (compare(version,version_grafted)<0):
            #nothing to do
            print ("information: scions ", scion, " version ", version, " from shelf " ,shelf," : current version ", version_grafted," is more recent.") 
         else:
         	print ("information: scions ", scion, " version ", version, " from shelf " ,shelf," already existing in depots.\n")
      else:
      	scion_graft_git_clone(entry_key,seed_dot_scion_path,sources_list_file_path,rootstock_path,shelf,scion,version)
        
      #end try except
   #end for
   scions_grafted_update(rootstock_path)
      


####################################################################
# scion graft operation functions
# read ($SCION_ROOTSTOCK/tauon/.scion.grafted.list) and graft each scion
####################################################################
def ungraft_all_scions(rootstock_path):
   #normalize path separator "/" 
   rootstock_path = rootstock_path.replace('\\','/')
   #
   dirs = os.listdir(rootstock_path)
   #
   for file in dirs:      
      
      if os.path.isdir(rootstock_path+"/"+file):
         print ("dir:", file, "\n" )
         ungraft_all_scions(rootstock_path+"/"+file)

      
      if os.path.islink(rootstock_path+"/"+file)==True:
         # remove symbolic link
         link_origin_path=os.readlink(rootstock_path+"/"+file)
         link_origin_real_path= os.path.realpath(link_origin_path)
         
         if os.path.isdir(link_origin_real_path):
            ungraft_all_scions(link_origin_real_path)
      
         try:
         	print ("ungraft: remove link: ", (rootstock_path+"/"+file), "\n") 
         	os.remove(rootstock_path+"/"+file) 
         except OSError:
            print ("error: cannot remove link on: ",(rootstock_path+"/"+file), "\n" )
 
#      
def graft_scion(rootstock_path,scion_path):
   #
   #print ("graft scion from: ",scion_path)
   #
   try:
      dirs = os.listdir(scion_path)
   except OSError:
      print ("error: cannot list dir: ", scion_path, "\n")
      return
   #
   for file in dirs:
      #.scion directory will not processed
      if(file==scion_hidden_dir):
      	continue
      #
      if not os.path.lexists(rootstock_path+"/"+file):
         # make symbolic link
         try:
            os.symlink(scion_path+"/"+file,rootstock_path+"/"+file) 
            print ("graft : make link from: ", scion_path+"/"+file," to ",(rootstock_path+"/"+file), "\n")
         except OSError:
            print ("error: cannot make link on: ", (rootstock_path+"/"+file), "\n")
      else:
         if os.path.isdir(scion_path+"/"+file):
            print ("dir:", file, "\n" )
            graft_scion(rootstock_path+"/"+file,scion_path+"/"+file)
         else:
            print ("error: file already exist: ", (rootstock_path+"/"+file), "\n")

#
def graft_scions(rootstock_path):
   # read and cached ($SCION_ROOTSTOCK/tauon/.scion.grafted.list)
   scions_grafted_cache(rootstock_path)
   #
   for entry in scions_grafted_dictionary.values():
      #get scion local location   
      try:
         shelf, scion, version, location, path = extract_scions_grafted_entry(entry)
      except IndexError:
         ungraft_all_scions(rootstock_path+"/"+rootstock_trunk_dir)
         print ("error : missing parameters in line ", entry,"\n. ungraft all\n") 
         sys.exit(1)
      # graft scion from local location on rootstock trunk
      location_realpath=os.path.realpath(os.path.expandvars(location))+"/"+scion_stem_dir #+"/"+src_dir
      #
      graft_scion(rootstock_path+"/"+rootstock_trunk_dir,location_realpath)

#
def graft_update(rootstock_path):
  #
  scions_grafted_cache(rootstock_path)
  #cearte seed list
  for entry_key, entry_line in scions_grafted_dictionary.items():
    #
    try:
      shelf_grafted, scion_grafted, version_grafted, location_grafted, seed_dot_scion_path_grafted = extract_scions_grafted_entry(entry_line)
    except IndexError:
      print ("error : missing parameters in grafted entry line", entry_line, "\n")
      exit(0)
    # no seed .scion
    if(len(seed_dot_scion_path_grafted)==0):
      continue
    #
    if(not seed_dot_scion_path_grafted in seeds_grafted_dictionnary):
      seeds_grafted_dictionnary[seed_dot_scion_path_grafted]=seed_dot_scion_path_grafted
      print ("added seeds .scion: ",seed_dot_scion_path_grafted)
  #
  for entry_key, entry_line in seeds_grafted_dictionnary.items():
    seed_dot_scion_path = entry_line
    #to do retrieve seed depot path 
    print("seed update : ",seed_dot_scion_path)
    scion_graft_scions_update(seed_dot_scion_path,seed_dot_scion_path+'/'+scion_sources_list_file,rootstock_path)
  
####################################################################
# # scion.py seeding --version [master|v.0.1.0.1] https://github.com/lepton-distribution/lepton-seed.scions.git [optional path to .scion directory default scion/.scion]
#    - clone seed depot in rootstock/depot/{extract prefix name of depot (prefix).git} 
#    - get ramification and source list
#    - clone all depot specifyed in ramification
#    - grafted list is updated
# scion seed functions. retrieve  .scion.ramifications and .scion.sources.list
#
####################################################################
#
def scion_seed_find_dot_scion(path):
  # walk in depot tree and find all .scion directories 
  try:
    dirs = os.listdir(path)
  except OSError:
    print ("error: cannot list dir: ", path, "\n")
    return
  #
  for entry in dirs:
    if not os.path.isdir(path+"/"+entry):
      continue
    #
    #print ("dir:", entry, "\n" )     
    #.scion directory
    if(entry==scion_hidden_dir):
      return path+"/"+entry
    
    found_path=scion_seed_find_dot_scion(path+"/"+entry)
    if(found_path==""):
      continue
    #
    return found_path
  #end for
  #  .scion not found
  return ""

#
def scion_seed_git_clone(rootstock_path, seed_url, seed_version, seed_scion_path="scion/.scion"):
  #
  parsed_seed_url=urlparse(seed_url)
  #extract prefix name of git depot
  git_depot_path = parsed_seed_url.path
  git_depot_prefix_name=os.path.splitext(os.path.basename(git_depot_path))[0]
  #
  # local or url
  if len(parsed_seed_url.scheme)>0: # remote url 
    # if distant check if already downloaded
    local_seed_depot_path=rootstock_path+"/"+rootstock_depots_dir+"/"+git_depot_prefix_name+"/"+seed_version
    #check if local git depot exists
    if not os.path.exists(local_seed_depot_path+"/.git"):
      # git clone -b v-0.0.0.1 --single-branch git://ks354041.kimsufi.com/scion-shelves/lepton-kernel.scion.git ./lepton/kernel/v-0.0.0.1
      git_command="git clone -b "+seed_version+" --single-branch "+seed_url+" "+local_seed_depot_path
      # execute git command
      os.system(git_command)
      if not os.path.exists(local_seed_depot_path+"/.git"):
        sys.exit("error: cannot download : "+seed_url)
      else:
        print("seed ", seed_url," version: ",seed_version," is downloaded in : ",local_seed_depot_path)
    else:
      print("information: seed ", seed_url," version: ",seed_version," already exists in : ",local_seed_depot_path)
      #update 
      if os.path.exists(local_seed_depot_path+"/.git"):
        # git pull
        git_command="git pull"
        # execute git command
        try:
          retcode = subprocess.check_call(git_command, shell=True, cwd = local_seed_depot_path)
          if retcode < 0:
            print("error: ", git_command," : ", -retcode, file=sys.stderr)
          else:
            print("seed from depot ", seed_url ," update succeed: ", retcode, file=sys.stderr)
        except subprocess.CalledProcessError as e:
          print("error: execution failed:", e, file=sys.stderr)

    #
    return local_seed_depot_path
  #else: #local path
 

#
def scion_seed_seeding(rootstock_path, seed_url, seed_version, seed_scion_path="scion/.scion"):
  #
  parsed_seed_url=urlparse(seed_url)
  # local or url
  if len(parsed_seed_url.scheme)>0: # remote url 
    local_seed_depot_path = scion_seed_git_clone(rootstock_path, seed_url, seed_version, seed_scion_path)
  else:
    local_seed_depot_path = seed_url
  #
  seed_dot_scion_path = scion_seed_find_dot_scion(local_seed_depot_path)
  if(seed_dot_scion_path =="" ):
    print ("error: .scion entry not found in: ",local_seed_depot_path)
    sys.exit(0)
  #
  print (".scion entry found in: ",seed_dot_scion_path)
  #
  scion_graft_scions_update(seed_dot_scion_path,seed_dot_scion_path+'/'+scion_sources_list_file,rootstock_path)


####################################################################
# install scion tools functions ~/.scion.settings/ 
####################################################################
def scion_install(home_path, rootstock_path):
    #check if already installed
    home_scion_settings_dir = home_path+"/"+scion_settings_dir
    dir = os.path.dirname(home_scion_settings_dir+"/")
    if not os.path.exists(dir):
      #if not installed: create ~/.scion/
      grow_branch(home_scion_settings_dir)
      grow_branch(home_scion_settings_dir+"/bin")
      #copy myself (scion.py) in  ~/.scion/
      shutil.copy2(sys.argv[0], home_scion_settings_dir+"/bin")
      #to dochange .profile

    grow_branch(rootstock_path+"/"+rootstock_depots_dir)
    grow_branch(rootstock_path+"/"+rootstock_trunk_dir)

    #scion building. to do : move in depots directory. 

    building_scion_path = rootstock_path+"/"+rootstock_depots_dir+"/"+lepton_shelf_dir+"/"+building_scion_dir
    
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/building/projects")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/building/staging/lib")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/building/output")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch/arm")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch/cortexm")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch/synthetic")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch/synthetic/x86")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch/synthetic/x86_static")
    grow_branch(building_scion_path+"/"+scion_stem_dir+"/sys/root/src/kernel/core/arch/win32")
    
    #
    #copy this script or make symbolic link from this script to bin 
    #
    set_active_rootstock_path(scion_rootstock_active_file_path,rootstock_path)
    #

def main():
  #main part
  print ("python version: ", sys.version)

  # init variable
  home_path = expanduser("~")
  scion_settings_path=home_path+"/"+scion_settings_dir
  scion_rootstock_active_file_path=scion_settings_path+"/"+scion_rootstock_active_file
  current_active_rootstock = get_active_rootstock_path(scion_rootstock_active_file_path)
  print ("current active rootstock path: ", current_active_rootstock) 
  #
  current_scion_path = get_current_scion_path()
  if(len(current_scion_path)<=0):
    print ("error : it's not scion directory: ", (scion_stem_dir+"/"+scion_hidden_dir), " not found") 
    sys.exit(1)

  scion_sources_list_file_path= current_scion_path+"/"+scion_hidden_dir+"/"+scion_sources_list_file
  print ("current scion path: ",current_scion_path, "\n")

  #seed default version
  default_seed_version="master"

  # create parsing arguments rules
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(help='commands')

  # command install
  scion_install_parser = subparsers.add_parser('install', help='install rootstock')
  scion_install_parser.set_defaults(which='install')

  # command seeding
  scion_seeding_parser = subparsers.add_parser('seeding', help='install rootstock')
  scion_seeding_parser.set_defaults(which='seeding')
  # command inventory
  scion_inventory_parser = subparsers.add_parser('inventory', help='scion inventory in rootstock ')
  scion_inventory_parser.set_defaults(which='inventory')
  # command clone
  scion_clone_parser = subparsers.add_parser('clone', help='clone all scions will be grafted')
  scion_clone_parser.set_defaults(which='clone')
  # command update
  scion_update_parser = subparsers.add_parser('update', help='update all scions in grafted list')
  scion_update_parser.set_defaults(which='update')

  # command graft-clean
  scion_graft_clean_parser = subparsers.add_parser('graft-clean', help='clean grafted list')
  scion_graft_clean_parser.set_defaults(which='graft-clean')
  # command graft-update
  scion_graft_update_parser = subparsers.add_parser('graft-update', help='update grafted seeds in grafted list')
  scion_graft_update_parser.set_defaults(which='graft-update')
  # command graft
  scion_graft_parser = subparsers.add_parser('graft', help='graft scions on rootstock')
  scion_graft_parser.set_defaults(which='graft')
  # command ungraft
  scion_ungraft_parser = subparsers.add_parser('ungraft', help='ungraft all scions rootstock')
  scion_ungraft_parser.set_defaults(which='ungraft')


  # arguments for command install
  if(len(current_active_rootstock)>0):
     scion_install_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_install_parser.add_argument("rootstock_path", default=current_active_rootstock)


  # arguments for command inventory 
  if(len(current_active_rootstock)>0):
     scion_inventory_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_inventory_parser.add_argument("rootstock_path", default=current_active_rootstock)


  # arguments for command seeding
  if(len(current_active_rootstock)>0):
     scion_seeding_parser.add_argument("--version",nargs='?', default=default_seed_version)
     scion_seeding_parser.add_argument("seed_url",nargs='?')
     scion_seeding_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_seeding_parser.add_argument("--version",nargs='?', default=default_seed_version)
     scion_seeding_parser.add_argument("seed_url",nargs='?')
     scion_seeding_parser.add_argument("rootstock_path",default=current_active_rootstock)

  # arguments for command clone
  if len(current_scion_path)>0:
     scion_clone_parser.add_argument("--seed", required=False, default=current_scion_path)
  else:#required
     scion_clone_parser.add_argument("--seed", required=True) 
  #
  if(len(current_active_rootstock)>0):
     scion_clone_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_clone_parser.add_argument("rootstock_path",default=current_active_rootstock)

  # arguments for command update
  if len(current_scion_path)>0:
     scion_update_parser.add_argument("--seed", required=False, default=current_scion_path)
  else:#required
     scion_update_parser.add_argument("--seed", required=True)  
  #
  if(len(current_active_rootstock)>0):
     scion_update_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_update_parser.add_argument("rootstock_path",default=current_active_rootstock)


  # arguments for command graft-clean
  if(len(current_active_rootstock)>0):
     scion_graft_clean_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_graft_clean_parser.add_argument("rootstock_path", default=current_active_rootstock)

  # arguments for command graft-clean
  if(len(current_active_rootstock)>0):
     scion_graft_update_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:#required
     scion_graft_update_parser.add_argument("rootstock_path", default=current_active_rootstock)

  # arguments for command graft
  if(len(current_active_rootstock)>0): 
     scion_graft_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else:
     scion_graft_parser.add_argument("rootstock_path", default=current_active_rootstock)


  # arguments for command ungraft
  if(len(current_active_rootstock)>0): 
     scion_ungraft_parser.add_argument("rootstock_path", nargs='?',default=current_active_rootstock)
  else: #required
     scion_ungraft_parser.add_argument("rootstock_path",default=current_active_rootstock)

   
  # parse commande line
  args = vars(parser.parse_args())
  print("args ",args,"\n") 

  #set env var
  os.environ[ENV_VAR_ACTIVE_ROOTSTOCK] = args["rootstock_path"]

  # install
  if args["which"]=="install":
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     scion_install(home_path,rootstock_path)


  # inventory 
  if args["which"]=="inventory":
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     inventory_active_rootstock_path(rootstock_path)


  # seeding
  if args["which"]=="seeding":
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     seed_url=args["seed_url"] 
     seed_version =args["version"] 
     #
     scion_seed_seeding(rootstock_path, seed_url, seed_version)
     

  # clone 
  if args["which"]=="clone": 
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
      #
     seed_path=args["seed"]
     #
     seed_dot_scion_path = scion_seed_find_dot_scion(seed_path)
     if(seed_dot_scion_path =="" ):
      print ("error: .scion entry not found in: ",seed_path)
      sys.exit(0)
     #
     scion_graft_scions_clone(seed_dot_scion_path,seed_dot_scion_path+'/'+sources_list_file_path,rootstock_path)

   # update
  if args["which"]=="update": 
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     seed_path=args["seed"]
     #
     seed_dot_scion_path = scion_seed_find_dot_scion(seed_path)
     if(seed_dot_scion_path =="" ):
      print ("error: .scion entry not found in: ",seed_path)
      sys.exit(0)
     #
     scion_graft_scions_update(seed_dot_scion_path,seed_dot_scion_path+'/'+sources_list_file_path,rootstock_path)

  # graft-clean
  if args["which"]=="graft-clean":
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     ungraft_all_scions(rootstock_path+"/"+rootstock_trunk_dir)
     #
     scions_grafted_clean(rootstock_path)

  # graft-update
  if args["which"]=="graft-update":
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     #ungraft_all_scions(rootstock_path+"/"+rootstock_trunk_dir)
     #
     graft_update(rootstock_path)
     #
     #graft_scions(rootstock_path)


  # graft
  if args["which"]=="graft": 
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     # ungraft all if previous graft operation was done 
     ungraft_all_scions(rootstock_path+"/"+rootstock_trunk_dir)
     #
     graft_scions(rootstock_path)

  # ungraft
  if args["which"]=="ungraft": 
     rootstock_path=args["rootstock_path"]
     #
     rootstock_path = os.path.realpath(rootstock_path)
     #
     ungraft_all_scions(rootstock_path+"/"+rootstock_trunk_dir)

#
main()
#end of script