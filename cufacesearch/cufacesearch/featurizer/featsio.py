import numpy as np

def read_features_from_tsv(tsv_file, verbose=False):
  # Initialize
  images_sha1s = []
  images_urls = []
  faces_bbox = []
  faces_feats = None

  # Read every line
  with open(tsv_file, 'rt') as infile:
    for line in infile:
      # Expected line format is:
      # sha1\ts3_url\t./local_path_to_be_ignored.jpg\tface_top\tface_bottom\tface_left\tface_right\tfeat_val1\t...\n
      fields = line.strip().split('\t')
      tmp_sha1 = fields[0]
      # cast face bbox coordinates to integers
      tmp_bbox = [int(x) for x in fields[3:7]]
      # cast face features to floats and as numpy array
      tmp_feat = np.expand_dims(np.fromstring(' '.join(fields[7:]), dtype=np.float32, sep=" "), axis=0)
      if tmp_feat.any():
        images_sha1s.append(tmp_sha1)
        images_urls.append(fields[1])

        # reorder in left, top, right, bottom
        faces_bbox.append(tuple([tmp_bbox[2], tmp_bbox[0], tmp_bbox[3], tmp_bbox[1]]))

        if faces_feats is None:
          faces_feats = tmp_feat
        else:
          try:
            faces_feats = np.concatenate((faces_feats, tmp_feat))
          except Exception as inst:
            print faces_feats.shape, tmp_feat.shape, tmp_feat, fields
            raise inst
      else:
        if verbose:
          print 'Skipping face {} in image {} without feature.'.format(tmp_bbox, tmp_sha1)
        pass

  return images_sha1s, images_urls, faces_bbox, faces_feats

def get_faces_ids_features(tsv_file, verbose=False):
  images_sha1s, _, faces_bbox, faces_feats = read_features_from_tsv(tsv_file)
  # build face_id as: imagesha1_bbox
  faces_ids = [sha1+"_"+"_".join([str(x) for x in faces_bbox[i]]) for i,sha1 in enumerate(images_sha1s)]
  if verbose:
    print faces_feats.shape
  return faces_ids, faces_feats

def load_face_features(base_path, verbose=False):
  import os
  import numpy as np

  # initialize
  all_face_ids = []
  all_features = None

  # explore all subfolders from base_path to get all 'part-*' files
  if os.path.isfile(base_path):
    if verbose:
      print "Reading features from {}".format(base_path)
    faces_ids, np_faces_feats = get_faces_ids_features(base_path)
    all_face_ids.extend(faces_ids)
    all_features = np_faces_feats
  else:
    print "Reading features in path: {}".format(base_path),
    for root, dirs, files in os.walk(base_path):
      for basename in files:
        # TODO: allow features files not starting with 'part-'
        if basename.startswith('part-'):
          # read each valid file to get face_ids, features
          valid_file = os.path.join(root, basename)
          if verbose:
            print "Reading features from {}".format(valid_file)
          faces_ids, np_faces_feats = get_faces_ids_features(valid_file)
          all_face_ids.extend(faces_ids)
          if all_features is None:
            all_features = np_faces_feats
          else:
            all_features = np.concatenate((all_features, np_faces_feats), axis=0)
          if verbose:
            print "We have {} faces with features shape {}.".format(len(all_face_ids), all_features.shape)
          if not verbose:
            print ".",
  print ""
  if all_features is not None:
    print "We have {} faces with features shape {}.".format(len(all_face_ids), all_features.shape)

  return all_face_ids, all_features