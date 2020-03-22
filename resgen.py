import struct                   # Working with the files in binary
import os                       # Numerous file functions 
import zipfile                  # Outputting map archive
import json                     # Config file
import re                       # Entdata lowercase writeback
from chardet import detect      # Detecting the entdata charset
#import cProfile

skybox_sides = [ "up", "dn", "lf", "rt", "ft", "bk" ] # The 6 sides of the skybox files
file_types = [ "wad", "tga", "spr", "mdl", "wav" ] # The file types that relate to external resources we want to capture
bad_string_contents = [ '\\\\', ':', '..' ] # HL will ignore resources read from res files if they contain any of these strings
script_directory = os.path.dirname((os.path.realpath(__file__)))

default_resources = []
custom_resources = []
map_file_info = {}

def read_bsp(filename):
        map_file_info['external_wad'] = False
        map_file_info['name'] = os.path.splitext(os.path.basename(filename))[0]
        map_file_info['filename'] = filename

        file_handle = open(filename, mode='rb')
        bsp_version = map_file_info['bsp_version'] = read_int(file_handle)
        if bsp_version != 30: # Check the BSP version before processing the rest of the file
                print('Error: Unexpected BSP version. Check file is a goldsrc map')
                return 1

        # Get the entdata offset and size
        entdata_start = map_file_info['entdata_start'] = read_int(file_handle)      
        entdata_size = map_file_info['entdata_size'] = read_int(file_handle)
        
        # Seek past the planes lumpinfo and read the file offset for the texture data
        file_handle.seek(20) 
        tex_data_start = read_int(file_handle)

        # First int is the number of textures
        file_handle.seek(tex_data_start) 
        tex_count = map_file_info['tex_count'] = read_int(file_handle)

        # Next x * int blocks are the offsets for each texture. x = texture count
        tex_offset_format = str(tex_count) + 'i' # x * int
        tex_offset_len = struct.calcsize(tex_offset_format) # Get total size of texture offsets number of bytes for x * int
        tex_offset_data = struct.unpack(tex_offset_format, file_handle.read(tex_offset_len)) # Read the offsets
         
        for tex_offset in tex_offset_data:

                # Just read the texture mip offset data
                file_handle.seek(tex_data_start + tex_offset + 24) # 24 = char[16] for texture name, and 2 x int (4 bytes each) for texture width / height
                tex_mip_offsets = struct.unpack('4i', file_handle.read(struct.calcsize('4i')))# tex_data = struct.unpack('16s6i', file_handle.read(struct.calcsize('16s6i')))
                
                # Loop through each mip offset. If the offsets for each mip level are 0 the texture must be in a external texture file
                for tex_mip_offset in tex_mip_offsets:
                        if tex_mip_offset == 0:
                                map_file_info['external_wad'] = True
                                break # I want to break out twice since we know textures are external now. Using the below statements to do this.
                        else:
                                continue  # Only executed if the inner loop did NOT break
                        break  # Only executed if the inner loop DID break
                
        # Seek to the location of the entity data and calculate end offset of entdata
        file_handle.seek(entdata_start) 

        # Read the entity data and create an .ent file 
        entdata_raw = map_file_info['entdata_raw'] = file_handle.read(entdata_size)

        # Grab the encoding for later decoding, this is usually acsii, but sometimes not.
        entdata_encoding = map_file_info['entdata_encoding'] = detect(entdata_raw)['encoding']
        entdata_lines = entdata_raw.splitlines()
        for line in entdata_lines:        
                if line[0] == 0 or line[0] == 123 or line[0] == 125: # Ignore 0x0, { and }
                        continue

                # Convert the raw bytes to a string and strip whitespace from end. Typically \n, but instances of \r depending on compiler I guess.
                line = line.decode(entdata_encoding).rstrip()

                keyvalue_pair = line.split(' ', 1)
                ent_key = keyvalue_pair[0].strip('"')
                ent_value = keyvalue_pair[1].strip('"')
                
                if ent_key == 'wad' and map_file_info['external_wad']:                        
                        ent_value = ent_value.rstrip(';') # Remove the end colon to avoid a blank item at the end of the array after split
                        wads = ent_value.split(';') # Each wad path is seperated by a semicolon
                        for wad in wads:
                                wad = os.path.basename(wad) # Get the .wad file name from the path
                                add_resource(wad)

                elif ent_key == 'skyname':
                        for side in skybox_sides: # Each skybox has a 6 sides, in seperate files, so add each file
                                add_resource('gfx/env/' + ent_value + side + '.tga')

                elif ent_key == 'replacement_model': # Custom to TFC. Allows mappers to change player model
                        add_resource('models/player/' + ent_value + '/' + ent_value + '.mdl')

                else:
                        # Since the file types we want are 3 characters long e.g. ".mdl", Continue if the len - 4 character from the end is a '.'
                        # This helps filter out all the values like "speed" "1000.5"
                        ent_value_len = len(ent_value)
                        if ent_value_len > 4 and ent_value[ent_value_len - 4] == '.':
                                # Check if it's a file type we should include
                                extension = os.path.splitext(ent_value)[1].lstrip('.')
                                if extension in file_types:
                                        #print(keyvalue_pair)
                                        if extension == 'wav': # Sound files are missing the parent directory, add it.
                                                ent_value = 'sound/' + ent_value
                                        add_resource(ent_value)
        file_handle.close()

def add_resource(resource):
        # Skip already added resources
        if resource in custom_resources:
                return 0
        
        # Skip default resources
        if is_default_resource(resource):
                return 0
        
        # Check for bad strings in the resource
        for bad_string in bad_string_contents:
                if resource.find(bad_string) != -1:
                        print("Skipping: Bad string in value: " + resource)
                        return 0

        # Note: Paths in hlds / bsp always uses '/' for path seperators regardless of system. '\' is an escape character. 
        # Sometimes mappers screw up. e.g. "ambience\zhans.wav" equates to ambience\hans.wav'
        # The server will fail to transmit the file to the clients. So lets fix this in the .res file
        # The BSP also needs fixing. If the person running this script enables entdata_writeback, we'll fix it there!
        resource = resource.replace("\\", "/")

        # Add to custom resource list
        custom_resources.append(resource)              

        # If the file is a model, check whether the textures are external
        # BUGBUG: This will check the t.mdl file also TODO: Fix
        resource_file_buf = os.path.splitext(resource)
        if resource_file_buf[1] == '.mdl' and has_mdl_external_texture(resource):
                add_resource(resource_file_buf[0] + 't.mdl')
        return 0

def read_default_resources():
        global  default_resources
        
        for file_type in file_types:
                default_resource_file = 'default' + os.path.sep  + config_data['game']['mod'] + '_' + file_type + '.ini'
                file = open(script_directory + os.path.sep + default_resource_file, 'r')
                default_resources += file.read().splitlines()
                file.close()

        return len(default_resources)

def has_mdl_external_texture(resource):
        model_path = config_data['resources']['input_dir'] + os.path.sep + resource
        try:
                file_handle = open(model_path, mode='rb')
        except FileNotFoundError:
                print("File not found. Unable to check for external model texture file: " + resource)
                return False

        file_handle.seek(180) # Skip 180 bytes into the mdl header to get the texture count
        model_tex_count = read_int(file_handle) # Read the # of textures in the model
        file_handle.close()

        # If the texture count is 0 then there will be an external modelT.mdl
        return True if model_tex_count == 0 else False

def is_default_resource(resource):
        if resource in default_resources:
                return 1
        return 0

def read_all_maps():        
        map_paths = []
        for r, d, f in os.walk(config_data['resources']['input_dir'] + os.path.sep + 'maps'):
                for file in f:
                        if '.bsp' in file:
                                map_paths.append(os.path.join(r, file))

        for map_path in map_paths:
                handle_map(map_path)

def handle_map(map_path):
        global custom_resources
        
        # Read the resources from the map BSP file
        read_bsp(map_path)

        do_lowercase = config_data['resources']['enforce_lowercase']
        map_name = map_file_info['name']
        
        # First lets set the resources in the list to lowercase
        if do_lowercase:
                custom_resources = [resource.lower() for resource in custom_resources]

        print("------------------------------------" + map_name + "------------------------------------")

        # Create the res file
        resource_count = len(custom_resources)
        if resource_count == 0:
                print("[INFO] No custom resources detected. res file not needed")
        else:
                create_resfile()
                print("[DONE] Created resource file " + map_name + ".res. Total: " + str(resource_count) + " custom resources")

        # Add these resources after the res file is generated, because we want to include them in the process below
                add_resource("maps/" + map_name + '.res')
        add_resource('maps/' + map_name + '.bsp')
        add_resource('maps/' + map_name + '.txt')

        # Kind of hacky, but run the lowercase again. TODO: See if this can be completed nicely in the block above
        if do_lowercase:
                custom_resources = [resource.lower() for resource in custom_resources]

        # Check if the resources exists locally
        missing_resource = False
        if config_data['resources']['check_exists']:
                for file in custom_resources:
                        if not is_exist_locally(file):
                                extension = os.path.splitext(file)[1].lstrip('.')
                                if extension == 'txt' and config_data['resources']['ignore_missing_txt']: 
                                        print("[INFO] Local file not found: " + file + " Config: ignore_missing_txt is True. Ignoring")
                                else:
                                        print("[ERROR] Local file not found: " + file)
                                        missing_resource = True

        # Enforce lowercase on resources.
        # Usually servers and http fast downloads are linux, which is case sensitive. Clients are windows, which is not
        # A problem is caused when the case of the file and the string in the entity are different. The server won't find the file.
        # Note: Sometimes mappers re-use the same resource with different case too, which becomes a mess.
        # Easiest solution is to enforce lowercase on all files, and write this back to the bsp file
        if do_lowercase:
                # Change the resources on the disk lowercase
                set_lowercase_disk_resources()

                # Write back the resources as lowercase in the bsp entdata
                # This also fixes situations where a mapper uses '\' instead of '/'. The engine sees '\' as an escape char.
                if config_data['resources']['entdata_writeback']:
                        set_lowercase_entdata_writeback()
                        print("[DONE] Wrote sanitized entdata to " + map_name + ".bsp. Total: " + str(map_file_info['entdata_size']) + " bytes")
        
        # Create the zip archive
        if config_data['archive']['create']:
                if missing_resource:
                        print("[ERROR] Skipping zip archive creation as local resource files are missing.")
                else:
                        create_map_archive()

        # cleanup before the next map
        clear_resource_lists()

def clear_resource_lists():
        custom_resources.clear()
        map_file_info.clear()

def is_exist_locally(resource):
        return os.path.isfile(config_data['resources']['input_dir'] + os.path.sep + resource)

def create_map_archive():
        # Check if the output directory specified in the config is absolute or relative
        zip_output_dir = config_data['archive']['output_dir']
        if not os.path.isabs(zip_output_dir):
                zip_output_dir = script_directory + os.path.sep + zip_output_dir

         # Create the output directory if it doesn't exist already
        if (not os.path.exists(zip_output_dir)):
                os.mkdir(zip_output_dir)

        # Create the zip file
        zip_file_count = 0
        zip_name = map_file_info['name'] + '.zip'
        zip_handle = zipfile.ZipFile(zip_output_dir + os.path.sep + zip_name, 'w', compression=zipfile.ZIP_DEFLATED)
        for file in custom_resources:
                try:
                        zip_handle.write(config_data['resources']['input_dir'] + os.path.sep + file, file)
                        zip_file_count += 1
                except FileNotFoundError:
                        print("[ERROR] File not found. Unable to add resource to archive: " + file)
        zip_handle.close()

        print("[INFO] Added " + str(zip_file_count) + " files to " + zip_name)
        
import sys
def set_lowercase_disk_resources():
        # Set resources files on disk to lowercase
        # BUGBUG: I realise this won't work on linux. Needs rewriting to list the directory and loop through the files.
        for resource in custom_resources:
                try:
                        os.rename(config_data['resources']['input_dir'] + os.path.sep + resource, config_data['resources']['input_dir'] + os.path.sep + resource.lower())
                except:
                        print("[ERROR] Unable to set resource to lowercase: " + resource)

def set_lowercase_entdata_writeback():
        new_entdata_raw = map_file_info['entdata_raw']
        for resource in custom_resources:
                # wav files don't need the parent "sound/" directory, remove it.
                extension = os.path.splitext(resource)[1].lstrip('.')
                if extension == 'wav': 
                        resource = resource.replace("sound/", "")

                # BUGBUG TODO: Need to handle "skybox" key e.g. 2Desert becomes 2desert.
                if extension == 'tga':
                        continue 

                # Start by escaping the resource string. e.g. "." becomes "\." i.e "ambience/zhans\.wav"
                resource_escaped = re.escape(resource)

                # Replace the path seperator "/"" so it matches both "\"" and "/""
                # This is so we can fix mappers that accidently use "\" in their string. Thus screwing up their map.
                # e.g. A sound with the value "ambience\zhans.wav" ends up bein interpretted by the HL engine as ambience\hans.wav' 
                pattern = resource_escaped.replace("/", "[\\\\\\/]") # i.e. ambience[\\\/]zhans\.wav 
                try:
                        # Case insensitive so "models/xmasblock/Santa_chimney.mdl" becomes "models/xmasblock/santa_chimney.mdl"
                        # If we have lowercase everywhere, server admins will find it easier to manage the game content on linux game/http:fastdl servers
                        map_file_info['entdata_raw'] = re.sub(pattern.encode(map_file_info['entdata_encoding']), resource.encode(map_file_info['entdata_encoding']), map_file_info['entdata_raw'], flags=re.IGNORECASE)
                except Exception as e:
                        print('Failed to re.sub entdata for writeback: '+ str(e))

        if len(map_file_info['entdata_raw']) == len(new_entdata_raw):
                file_handle = open(map_file_info['filename'], mode='r+b') # Open as r+b so we can seek and write in binary
                file_handle.seek(map_file_info['entdata_start'])
                file_handle.write(new_entdata_raw)
                file_handle.close()
        else:
                print("Error: Entdata size does not match. Aborting to avoid corrupting the bsp")

        #create_entfile(new_entdata_raw, map_file_info['name'] + "_new")
        #create_entfile(map_file_info['entdata_raw'], map_file_info['name'] + "_old")

def create_resfile():
        file_handle = open(config_data['resources']['input_dir'] + os.path.sep + 'maps' + os.path.sep + map_file_info['name'] + ".res", "w")  
        file_handle.write("// Generated with goldsrc_map_packer: https://github.com/ben-watch/goldsrc_map_packer\n") # on " + datetime.datetime.now().strftime("%Y-%m-%d") + "\n")
        file_handle.write('\n'.join(custom_resources)) 
        file_handle.close()
                        
def read_int(file_handle):
        return struct.unpack('i', file_handle.read(4))[0] # int = 4 bytes

def create_entfile(entdata_raw, out_file_name):
        file_handle = open(config_data['resources']['input_dir'] + os.path.sep + 'maps' + os.path.sep + out_file_name + ".ent", "wb")  
        file_handle.write(entdata_raw) 
        file_handle.close()

#pr = cProfile.Profile()
#pr.enable()

# Load the configuration file
with open('config.json') as json_data_file:
    config_data = json.load(json_data_file)

read_default_resources()
read_all_maps()
     
#pr.disable()
#pr.print_stats(sort='tottime')
