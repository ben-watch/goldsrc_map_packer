import struct
import os
import zipfile
from chardet import detect

#import cProfile

ROOT_GAME_DIR = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Half-Life\\tfc_downloads\\" # The path to use for resources
MOD_NAME = "tfc"  # Hardcoded for now. This changes the default resource files read
#ENFORCE_LOWERCASE = 1

skybox_sides = [ "up", "dn", "lf", "rt", "ft", "bk" ] # The 6 sides of the skybox files
file_types = [ "wad", "tga", "spr", "mdl", "wav" ] # The file types that relate to external resources we want to capture
bad_string_contents = [ '\\\\', ':', '..' ] # HL will ignore resources read from res files if they contain any of these strings
script_directory = os.path.dirname((os.path.realpath(__file__)))

default_resources = []
custom_resources = []
resource_warnings = []
map_file_info = {}

# Note: HL resources always uses '/' for path seperators regardless of system
def read_bsp(filename):
        map_file_info['external_wad'] = False
        map_name = map_file_info['name'] = os.path.splitext(os.path.basename(filename))[0]
                     
        file_handle = open(filename, mode='rb')
        bsp_version = read_int(file_handle)
        if bsp_version != 30: # Check the BSP version before processing the rest of the file
                print('Error: Unexpected BSP version. Check file is a goldsrc map')
                return 1

        # Get the entdata offset and size
        entdata_start = read_int(file_handle)      
        entdata_size = map_file_info['entdata_size'] = read_int(file_handle)
        
        # Seek past the planes lumpinfo and read the file offset for the texture data
        file_handle.seek(20) 
        tex_data_start = read_int(file_handle)

        # First int is the number of textures
        file_handle.seek(tex_data_start) 
        tex_count = map_file_info['entdata_size'] = read_int(file_handle)

        # Next x * int blocks are the offsets for each texture. x = texture count
        tex_offset_format = str(tex_count) + 'i' # x * int
        tex_offset_len = struct.calcsize(tex_offset_format) # Get total size of texture offsets number of bytes for x * int
        tex_offset_data = struct.unpack(tex_offset_format, file_handle.read(tex_offset_len)) # Read hte offsets
         
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
        entdata_offset_end = entdata_start + entdata_size

        # Read the entity data and grab the encoding, this is usually acsii, but sometimes not.
        entdata = file_handle.read(entdata_size) 
        map_file_info['entdata_encoding'] = detect(entdata)['encoding']
        entdata = entdata.splitlines()
        for line in entdata:        
                if line[0] == 0 or line[0] == 123 or line[0] == 125: # Ignore 0x0, { and }
                        continue

                # Convert the raw bytes to a string and strip whitespace from end
                # Typically \n, but instances of \r
                line = line.decode(map_file_info['entdata_encoding']).rstrip()

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
                                        if extension == 'wav': # Sound files are missing the base directory, add it.
                                                ent_value = 'sound/' + ent_value
                                        add_resource(ent_value)
        file_handle.close()

def add_resource(resource):
        # Skip already added resources
        if resource in custom_resources:
                return 1
        
        # Skip default resources
        if is_default_resource(resource):
                return 1
        
        # Check for bad strings in the resource
        for bad_string in bad_string_contents:
                if resource.find(bad_string) != -1:
                        resource_warnings.append("Bad string in value: " + resource)

        # Check if the resource exists locally
        if is_exist_locally(resource) == 0:
                resource_warnings.append("File not found: " + resource)

        # Add to custom resource list
        custom_resources.append(resource)              

        # If the file is a model, check whether the textures are external
        resource_file_buf = os.path.splitext(resource)
        if resource_file_buf[1] == '.mdl' and has_mdl_external_texture(resource):
                add_resource(resource_file_buf[0] + 't.mdl')
        return 0

def read_default_resources():
        global  default_resources
        
        for file_type in file_types:
                default_resource_file = 'default' + os.path.sep  + MOD_NAME + '_' + file_type + '.ini'
                file = open(script_directory + os.path.sep + default_resource_file, 'r')
                default_resources += file.read().splitlines()
                file.close()

        return len(default_resources)

def has_mdl_external_texture(resource):
        model_path = ROOT_GAME_DIR + os.path.sep + resource
        try:
                file_handle = open(model_path, mode='rb')
        except:
                resource_warnings.append("Unable to verify model texture file because model is missing: " + resource)
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
        for r, d, f in os.walk(ROOT_GAME_DIR + os.path.sep + 'maps'):
                for file in f:
                        if '.bsp' in file:
                                map_paths.append(os.path.join(r, file))

        for map_path in map_paths:
                read_bsp(map_path)

                print(map_file_info)
                print(custom_resources)
                #set_lowercase(custom_resources)
                
                map_name = map_file_info['name']
                create_resfile(custom_resources, map_name)
                
                add_resource("maps/" + map_name + '.res')
                add_resource('maps/' + map_name + '.bsp') 
                add_resource('maps/' + map_name + '.txt')

                if len(resource_warnings) == 0:
                        create_map_archive(custom_resources, map_name)

                clear_resource_lists()

def clear_resource_lists():
        custom_resources.clear()
        resource_warnings.clear()
        map_file_info.clear()

def is_exist_locally(resource):
        return os.path.isfile(ROOT_GAME_DIR + os.path.sep + resource)

def create_map_archive(resource_list, map_name):
        # Create the output directory if it doesn't exist already
        zip_output_dir = script_directory + os.path.sep + 'output'
        if (not os.path.exists(zip_output_dir)):
                os.mkdir(zip_output_dir)

        # Create the zip file
        zip_handle = zipfile.ZipFile(zip_output_dir + os.path.sep + map_name + '.zip', 'w', compression=zipfile.ZIP_DEFLATED)
        for file in resource_list:
                zip_handle.write(ROOT_GAME_DIR + file, file)
        zip_handle.close()

def set_lowercase(resource_list):
        map(str.lower, resource_list) # Set the list to lowercase

        # Set actual files to lowercase
        for resource in resource_list:
                os.rename(ROOT_GAME_DIR + resource, ROOT_GAME_DIR + resource.lower())

def create_resfile(resource_list, map_name):
        file_handle = open(ROOT_GAME_DIR + os.path.sep + 'maps' + os.path.sep + map_name + ".res", "w")  
        file_handle.write('\n'.join(resource_list)) 
        file_handle.close()
                        
def read_int(file_handle):
        return struct.unpack('i', file_handle.read(4))[0]

#pr = cProfile.Profile()
#pr.enable()

read_default_resources()
read_all_maps()
     
#pr.disable()
#pr.print_stats(sort='tottime')
