"""Flask API to expose the search index.
"""

import os
import sys
import time
import json
from datetime import datetime

from flask import Markup, flash, request, render_template, make_response
from flask_restful import Resource

from ..imgio.imgio import ImageMIMETypes, get_SHA1_img_type_from_B64, get_SHA1_img_info_from_buffer, \
  buffer_to_B64
from ..detector.utils import build_bbox_str_list


from socket import *
sock = socket()
sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

global_searcher = None
global_start_time = None
input_type = "image"

REFRESH_DELAY = 3600

class APIResponder(Resource):
  """Rest API class.
  """

  def __init__(self):
    self.searcher = global_searcher
    self.start_time = global_start_time
    self.input_type = input_type
    # This could be loaded from config?
    self.default_no_blur = True
    self.default_max_height = 120
    # how to blur canvas images but keep the face clean?
    self.valid_options = ["near_dup", "near_dup_th", "no_blur", "detect_only", "max_height", "max_returned"]

  def get(self, mode):
    """Get request. Will be fulfilled based on ``mode`` value in list:
     - ``byURL``
     - ``bySHA1``
     - ``byPATH``
     - ``byB64``
     - ``view_image_sha1``
     - ``view_similar_byURL``
     - ``view_similar_byB64``
     - ``view_similar_byPATH``
     - ``view_similar_bySHA1``

    :param mode: mode of the request
    :type mode: str
    :return: response (JSON) or HTML file for ``view_similar_byX`` modes.
    :rtype: dict
    """
    query = request.args.get('data')
    #query = unicode(request.args.get('data'), "utf8")
    options = request.args.get('options')
    if query:
      pid = os.getpid()
      print("[get.{}] received parameters: {}".format(pid, request.args.keys()))
      print("[get.{}] received data: ".format(pid)+query.encode('ascii','ignore'))
      print("[get.{}] received options: {}".format(pid, options))
      return self.process_query(mode, query, options)
    else:
      return self.process_mode(mode)

  def put(self, mode):
    """Put request.

    :param mode: mode of the request
    :type mode: str
    :return: response (JSON)
    :rtype: dict
    """
    return self.put_post(mode)

  def post(self, mode):
    """Post request.

    :param mode: mode of the request
    :type mode: str
    :return: response (JSON)
    :rtype: dict
    """
    return self.put_post(mode)

  def put_post(self, mode):
    """Deal with a ``put`` or ``post`` request.

    :param mode: mode of the request
    :type mode: str
    :return: response (JSON)
    :rtype: dict
    """
    pid = os.getpid()
    print("[put/post.{}] received parameters: {}".format(pid, request.form.keys()))
    print("[put/post.{}] received request: {}".format(pid, request))
    query = request.form['data']
    try:
      options = request.form['options']
    except:
      options = None
    print("[put/post.{}] received data of length: {}".format(pid, len(query)))
    print("[put/post.{}] received options: {}".format(pid, options))
    if not query:
      return {'error': 'no data received'}
    else:
      return self.process_query(mode, query, options)

  def process_mode(self, mode):
    """Deal with a mode request, either:

    - ``status``: get status and statistics about the search index.
    - ``refresh``: forces full refresh of the search index.

    :param mode: mode request
    :type mode: str
    :return: response (JSON)
    :rtype: dict
    """
    print("[api.{}.process_mode: log] received: {}".format(os.getpid(), mode))
    if mode == "status":
      return self.status()
    elif mode == "refresh":
      return self.refresh()
    elif mode == "check_all_updates":
      return self.check_all_updates()
    else:
      return {'error': 'unknown_mode: '+str(mode)+'. Did you forget to give \'data\' parameter?'}

  def process_query(self, mode, query, options=None):
    """Process the query

    :param mode: query mode
    :type mode: str
    :param query: query data
    :type query: str
    :param options:
    :type options: JSON string
    :return: response (JSON)
    :rtype: dict
    """
    start = time.time()
    if mode == "byURL":
      resp = self.search_byURL(query, options)
    elif mode == "bySHA1":
      resp = self.search_bySHA1(query, options)
    elif mode == "byPATH":
      resp = self.search_byPATH(query, options)
    elif mode == "byB64":
      resp = self.search_byB64(query, options)
    elif mode == "view_image_sha1":
      return self.view_image_sha1(query, options)
    elif mode == "view_similar_byURL":
      query_reponse = self.search_byURL(query, options)
      return self.view_similar_query_response('URL', query, query_reponse, options)
    elif mode == "view_similar_byB64":
      query_reponse = self.search_byB64(query, options)
      return self.view_similar_query_response('B64', query, query_reponse, options)
    elif mode == "view_similar_byPATH":
      query_reponse = self.search_byPATH(query, options)
      return self.view_similar_query_response('PATH', query, query_reponse, options)
    elif mode == "view_similar_bySHA1":
      query_reponse = self.search_bySHA1(query, options)
      return self.view_similar_query_response('SHA1', query, query_reponse, options)
    # elif mode == "byURL_nocache":
    #   resp = self.search_byURL_nocache(query, options)
    # elif mode == "bySHA1_nocache":
    #   resp = self.search_bySHA1_nocache(query, options)
    # elif mode == "byB64_nocache":
    #   resp = self.search_byB64_nocache(query, options)
    else:
      return {'error': 'unknown_mode: '+str(mode)}
    resp['Timing'] = time.time()-start
    return resp

  def get_options_dict(self, options):
    """Parse provided options.

    :param options: JSON string of the options
    :type options: str
    :return: (options_dict, errors)
    :rtype: tuple
    """
    errors = []
    options_dict = dict()
    if options:
      try:
        options_dict = json.loads(options)
      except Exception as inst:
        err_msg = "[get_options: error] Could not load options from: {}. {}".format(options, inst)
        print(err_msg)
        errors.append(err_msg)
      for k in options_dict:
        if k not in self.valid_options:
          err_msg = "[get_options: error] Unknown option {}".format(k)
          print(err_msg)
          errors.append(err_msg)
    return options_dict, errors

  def append_errors(self, outp, errors=[]):
    if errors:
      e_d = dict()
      if 'errors' in outp:
        e_d = outp['errors']
      for i,e in enumerate(errors):
        e_d['error_{}'.format(i)] = e
      outp['errors'] = e_d
    return outp

  def search_byURL(self, query, options=None):
    """Perform a search for the (list of) image(s) URL provided in query.

    :param query: comma separated list of image URLs
    :type query: str
    :param options: JSON string of the options
    :type options: str
    :return: response dictionary
    :rtype: dict
    """
    query_urls = self.get_clean_urls_from_query(query)
    options_dict, errors = self.get_options_dict(options)
    #outp = self.searcher.search_image_list(query_urls, options_dict)
    outp = self.searcher.search_imageURL_list(query_urls, options_dict)
    outp_we = self.append_errors(outp, errors)
    sys.stdout.flush()
    return outp_we

  def search_byPATH(self, query, options=None):
    """Perform a search for the (list of) image(s) paths provided in query.

    :param query: comma separated list of image paths
    :type query: str
    :param options: JSON string of the options
    :type options: str
    :return: response dictionary
    :rtype: dict
    """
    query_paths = query.split(',')
    options_dict, errors = self.get_options_dict(options)
    outp = self.searcher.search_image_path_list(query_paths, options_dict)
    outp_we = self.append_errors(outp, errors)
    sys.stdout.flush()
    return outp_we

  def search_bySHA1(self, query, options=None):
    """Perform a search for the (list of) image(s) SHA1 provided in query. Assumes these images have
    been indexed.

    :param query: comma separated list of image SHA1s.
    :type query: str
    :param options: JSON string of the options
    :type options: str
    :return: response dictionary
    :rtype: dict
    """
    query_sha1s = query.split(',')
    options_dict, errors = self.get_options_dict(options)
    # get the image URLs/paths from HBase and search
    # TODO: should we actually try to get features?
    rows_imgs = self.searcher.indexer.get_columns_from_sha1_rows(query_sha1s,
                                                                 columns=[self.searcher.img_column])
    # TODO: what shoudl we do if we get less rows_imgs than query_sha1s?
    query_imgs = [row[1][self.searcher.img_column] for row in rows_imgs]
    if self.searcher.file_input:
      outp = self.searcher.search_image_path_list(query_imgs, options_dict)
    else:
      outp = self.searcher.search_imageURL_list(query_imgs, options_dict)
    outp_we = self.append_errors(outp, errors)
    sys.stdout.flush()
    return outp_we

  def search_byB64(self, query, options=None):
    """Perform a search for the (list of) base64 encoded image(s) provided in query.

    :param query: comma separated list of base64 encoded images
    :type query: str
    :param options: JSON string of the options
    :type options: str
    :return: response dictionary
    :rtype: dict
    """
    query_b64s = [str(x) for x in query.split(',') if not x.startswith('data:')]
    options_dict, errors = self.get_options_dict(options)
    outp = self.searcher.search_imageB64_list(query_b64s, options_dict)
    outp_we = self.append_errors(outp, errors)
    sys.stdout.flush()
    return outp_we

  def refresh(self):
    """Forces a refresh of the search index.

    :return: response (JSON)
    :rtype: dict
    """
    # Force check if new images are available in HBase
    # Could be called if data needs to be as up-to-date as it can be but may take a while
    print("[api.{}.refresh: log] received refresh call".format(os.getpid()))
    if self.searcher:
      self.searcher.load_codes(full_refresh=True)
    # Likely to timeout before this message is sent
    return {'refresh': 'just run a full refresh'}

  def status(self):
    """Get the status of the search index. Will run a fast refresh if index has not been refreshed
    in the last 4 hours.

    :return: response (JSON)
    :rtype: dict
    """
    # prepare output
    print("[api.{}.status: log] received status call".format(os.getpid()))
    status_dict = {'status': 'OK'}

    status_dict['API_start_time'] = self.start_time.isoformat(' ')
    status_dict['API_uptime'] = str(datetime.now()-self.start_time)

    # Try to refresh on status call but at most every hour
    # The last refresh time should be shared accross workers when using gunicorn...
    if self.searcher.last_refresh:
      last_refresh_time = self.searcher.last_refresh
    else:
      last_refresh_time = self.searcher.indexer.last_refresh

    diff_time = datetime.now()-last_refresh_time
    if self.searcher and diff_time.total_seconds() > REFRESH_DELAY:
      self.searcher.load_codes()
      last_refresh_time = self.searcher.last_refresh

    status_dict['last_refresh_time'] = last_refresh_time.isoformat(' ')
    status_dict['nb_indexed'] = str(self.searcher.searcher.get_nb_indexed())
    return status_dict

  def check_all_updates(self):
    """Check for any unindexed update disregarding last update indexed time.

    :return: response (JSON)
    :rtype: dict
    """
    # prepare output
    print("[api.{}.check_all_updates: log] received check_all_updates call".format(os.getpid()))
    status_dict = {'status': 'OK'}

    status_dict['API_start_time'] = self.start_time.isoformat(' ')
    status_dict['API_uptime'] = str(datetime.now() - self.start_time)
    self.searcher.load_codes(check_all_updates=True)
    last_refresh_time = self.searcher.last_refresh
    status_dict['last_refresh_time'] = last_refresh_time.isoformat(' ')
    status_dict['nb_indexed'] = str(self.searcher.searcher.get_nb_indexed())
    return status_dict

  #TODO: Deal with muliple query images with an array parameter request.form.getlist(key)
  @staticmethod
  def get_clean_urls_from_query(query):
    """To deal with comma in URLs.

    :param query: list of comma separted URLs
    :type query: str
    :return: list of URLs
    :rtype: list
    """

    # tmp_query_urls = ['http'+str(x) for x in query.split('http') if x]
    # fix issue with unicode in URL
    from ..common.dl import fixurl
    tmp_query_urls = [fixurl('http' + x) for x in query.split('http') if x]
    query_urls = []
    for x in tmp_query_urls:
      if x[-1] == ',':
        query_urls.append(x[:-1])
      else:
        query_urls.append(x)
    print("[get_clean_urls_from_query: info] {}".format(query_urls))
    return query_urls

  def view_similar_query_response(self, query_type, query, query_response, options=None):
    """Build an HTML page showing the query results. Mostly for debugging.

    :param query_type: type of the query: ``B64``, ``URL``, ``PATH``, or ``SHA1``.
    :type query_type: str
    :param query: query data
    :type query: str
    :param query_response: response dictionary
    :type query_response: dict
    :param options: options JSON string
    :type options: str
    :return: HTML page showing the results.
    """
    if query_type == 'B64':
      # get :
      # - sha1 to be able to map to query response
      # - image type to make sure the image is displayed properly
      # - embedded format for each b64 query
      # TODO: use array parameter
      query_list = query.split(',')
      query_b64_infos = [get_SHA1_img_type_from_B64(q) for q in query_list if not q.startswith('data:')]
      query_urls_map = dict()
      for img_id, img_info in enumerate(query_b64_infos):
        query_urls_map[img_info[0]] = "data:"+ImageMIMETypes[img_info[1]]+";base64,"+str(query_list[img_id])
    elif query_type == "PATH" or (query_type == "SHA1" and self.searcher.file_input):
      # Encode query in B64
      query_infos = []
      query_list = query.split(',')
      # Get images paths from sha1s
      if query_type == 'SHA1' and self.searcher.file_input:
        rows_imgs = self.searcher.indexer.get_columns_from_sha1_rows(query_list, columns=[self.searcher.img_column])
        query_list = [row[1][self.searcher.img_column] for row in rows_imgs]
      query_list_B64 = []
      for q in query_list:
        with open(q,'rb') as img_buffer:
          query_infos.append(get_SHA1_img_info_from_buffer(img_buffer))
          query_list_B64.append(buffer_to_B64(img_buffer))
      query_urls_map = dict()
      for img_id, img_info in enumerate(query_infos):
        query_urls_map[img_info[0]] = "data:" + ImageMIMETypes[img_info[1]] + ";base64," + str(query_list_B64[img_id])
    elif query_type == "URL" or (query_type == "SHA1" and not self.searcher.file_input):
      # URLs should already be in query response
      pass
    else:
      print("[view_similar_query_response: error] Unknown query_type: {}".format(query_type))
      return None

    # Get errors
    options_dict, errors_options = self.get_options_dict(options)

    # Parse similar faces response
    all_sim_faces = query_response[self.searcher.do.map['all_similar_'+self.input_type+'s']]
    search_results = []
    print "[view_similar_query_response: log] len(sim_images): {}".format(len(all_sim_faces))
    for i in range(len(all_sim_faces)):
      # Parse query face, and build face tuple (sha1, url/b64 img, face bounding box)
      query_face = all_sim_faces[i]
      #print "query_face [{}]: {}".format(query_face.keys(), query_face)
      sys.stdout.flush()
      query_sha1 = query_face[self.searcher.do.map['query_sha1']]
      if query_type == "B64" or query_type == "PATH" or (query_type == "SHA1" and self.searcher.file_input):
        query_face_img = query_urls_map[query_sha1]
      else:
        query_face_img = query_face[self.searcher.do.map['query_url']].decode("utf8")
        #query_face_img = query_face[self.searcher.do.map['query_url']]
      if self.searcher.do.map['query_'+self.input_type] in query_face:
        query_face_bbox = query_face[self.searcher.do.map['query_'+self.input_type]]
        query_face_bbox_compstr = build_bbox_str_list(query_face_bbox)
      else:
        query_face_bbox_compstr = []
      img_size = None
      if self.searcher.do.map['img_info'] in query_face:
        img_size = query_face[self.searcher.do.map['img_info']][1:]
      out_query_face = (query_sha1, query_face_img, query_face_bbox_compstr, img_size)
      # Parse similar faces
      similar_faces = query_face[self.searcher.do.map['similar_'+self.input_type+'s']]
      #print similar_faces[self.searcher.do.map['number_faces']]
      out_similar_faces = []
      for j in range(similar_faces[self.searcher.do.map['number_'+self.input_type+'s']]):
        # build face tuple (sha1, url/b64 img, face bounding box, distance) for one similar face
        osface_sha1 = similar_faces[self.searcher.do.map['image_sha1s']][j]
        #if query_type == "PATH":
        if self.searcher.file_input:
          with open(similar_faces[self.searcher.do.map['cached_image_urls']][j], 'rb') as img_buffer:
            img_info = get_SHA1_img_info_from_buffer(img_buffer)
            img_B64 = buffer_to_B64(img_buffer)
          osface_url = "data:" + ImageMIMETypes[img_info[1]] + ";base64," + str(img_B64)
        else:
          osface_url = similar_faces[self.searcher.do.map['cached_image_urls']][j]
        osface_bbox_compstr = None
        if self.input_type != "image":
          osface_bbox = similar_faces[self.searcher.do.map[self.input_type+'s']][j]
          osface_bbox_compstr = build_bbox_str_list(osface_bbox)
        osface_img_size = None
        if self.searcher.do.map['img_info'] in similar_faces:
          osface_img_size = similar_faces[self.searcher.do.map['img_info']][j][1:]
        osface_dist = similar_faces[self.searcher.do.map['distances']][j]
        out_similar_faces.append((osface_sha1, osface_url, osface_bbox_compstr, osface_dist, osface_img_size))
      # build output
      search_results.append((out_query_face, [out_similar_faces]))

    # Prepare settings
    settings = dict()
    settings["no_blur"] = self.default_no_blur
    settings["max_height"] = self.default_max_height
    if "no_blur" in options_dict:
      settings["no_blur"] = options_dict["no_blur"]
    if "max_height" in options_dict:
      settings["max_height"] = options_dict["max_height"]

    headers = {'Content-Type': 'text/html'}

    #print search_results
    sys.stdout.flush()
    if self.input_type != "image":
      return make_response(render_template('view_similar_faces_wbbox.html',
                                         settings=settings,
                                         search_results=search_results),
                         200, headers)
    else:
      return make_response(render_template('view_similar_images.html',
                                           settings=settings,
                                           search_results=search_results),
                             200, headers)

  # Are these two methods really useful?
  def get_image_str(self, row):
    # TODO: use column_family and column_name from indexer
    return "<img src=\"{}\" title=\"{}\" class=\"img_blur\">".format(row[1]["info:s3_url"],row[0])

  def view_image_sha1(self, query, options=None):
    # Not really used anymore...
    query_sha1s = [str(x) for x in query.split(',')]
    # TODO: use column_family and column_name from indexer
    rows = self.searcher.indexer.get_columns_from_sha1_rows(query_sha1s, ["info:s3_url"])
    images_str = ""
    # TODO: change this to actually just produce a list of images to fill a new template
    for row in rows:
      images_str += self.get_image_str(row)
    images = Markup(images_str)
    flash(images)
    headers = {'Content-Type': 'text/html'}
    return make_response(render_template('view_images.html'),200,headers)