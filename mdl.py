import struct
import os

#	int					id;
#	int					version;
#	char				name[64];
#	int					length;
#	vec3_t				eyeposition;
#	vec3_t				min;
#	vec3_t				max;
#	vec3_t				bbmin;
#	vec3_t				bbmax;
#	int					flags;
#	int					numbones;
#	int					boneindex;
#	int					numbonecontrollers;
#	int					bonecontrollerindex;
#	int					numhitboxes;
#	int					hitboxindex;
#	int					numseq;
#	int					seqindex;
#	int					numseqgroups;
#	int					seqgroupindex;
#	int					numtextures;
#	int					textureindex;
#	int					texturedataindex;
#	int					numskinref;
#	int					numskinfamilies;
#	int					skinindex;
#	int					numbodyparts;		
#	int					bodypartindex;
#   [...]
# studiohdr_t;

#	char					name[64];
#	int						flags;
#	int						width;
#	int						height;
#	int						index;
# mstudiotexture_t;
studio_texture_fmt = '64ciiii'

#	char				name[64];
#	int					nummodels;
#	int					base;
#	int					modelindex; // index into models array
# mstudiobodyparts_t;
studio_bodyparts_fmt = '64ciii'

def read_mdl(filename):
    file_handle = open(filename, mode='rb')

    if (file_handle.read(4) == b'IDST' and read_int(file_handle) == 10):
        model_name = file_handle.read(64).decode('utf-8').split('\x00',1)[0]
        model_size = read_int(file_handle)
        print("Model Name: " + model_name + " Size: " + str(model_size))

        file_handle.seek(180) # Skip into the mdl header to get the numtextures
        model_tex_count = read_int(file_handle) 
        model_tex_offset = read_int(file_handle) 
        print("Texture Count: " + str(model_tex_count) + " Offset: " + str(model_tex_offset))

        file_handle.seek(4, 1) # Skip textureDataOffset?

        model_skin_count = read_int(file_handle) # Number of textures in each skin e.g. Domo = 3 (eye, mouth, fur)
        model_skin_fam_count = read_int(file_handle) # Number of skins on the model
        model_skin_offset = read_int(file_handle) 
        print("Skin Count: " + str(model_skin_count) + " Family Count: " + str(model_skin_fam_count) + " Offset: " + str(model_skin_offset))

        model_body_count = read_int(file_handle)
        model_body_offset = read_int(file_handle) 
        print("Body Count: " + str(model_body_count) + " Offset: " + str(model_body_offset))

        texture_names = []
        for i in range(model_tex_count):
            file_handle.seek(model_tex_offset + (i * struct.calcsize(studio_texture_fmt)))
            texture_name = file_handle.read(64).decode()
            texture_names.append(texture_name)
            print("Texture " + str(i) + ": " +  texture_name)

        for i in range(model_body_count):
            file_handle.seek(model_body_offset + (i * struct.calcsize(studio_bodyparts_fmt)))
            body_part_name = file_handle.read(64).decode()
            print("Body " + str(i) + ": " +  body_part_name)

        for i in range(model_skin_fam_count):
            file_handle.seek(model_skin_offset + (i * 2 * model_skin_count)) # 2 = size of short 
            skin_tex_index = read_short(file_handle) # BUG? Assumption here that the skin is always the first texture if there are more than  1.
            print("Skin " + str(i) + ": " + "Texture index = " + str(skin_tex_index) + " = " + texture_names[skin_tex_index])

    file_handle.close()

def read_int(file_handle):
        return struct.unpack('i', file_handle.read(4))[0] # int = 4 bytes

def read_short(file_handle):
        return struct.unpack('2b', file_handle.read(2))[0] # short = 2 bytes

read_mdl("C:\\Program Files (x86)\\Steam\\steamapps\\common\\Half-Life\\tfc_downloads\\models\\player\\\domokun_r\\\domokun_r.mdl")


      