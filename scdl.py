#!/usr/bin/python3
import os
import requests
import eyed3
import re
import argparse
import json
from multiprocessing import Pool

CONFIG_PATH = './configs.json'

class SoundCloudClient(object):
    def __init__(self, client_id, save_dir):
        self.client_id = client_id
        self.save_dir = save_dir
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)

    @staticmethod
    def detect_url(url):
        track_pattern = r'^https:\/\/soundcloud\.com\/[^\/]+\/([^\/]+)$'
        playlist_pattern = r'^https:\/\/soundcloud\.com\/[^\/]+\/sets\/([^\/]+)$'
        if re.match(track_pattern, url):
            return {
                'type': 'track', 
                'name': re.search(track_pattern, url).group(1)
            }
        elif re.match(playlist_pattern, url):
            return {
                'type': 'playlists',
                'name': re.search(playlist_pattern, url).group(1)
            }
        else:
            return None

    def convert_url_to_id(self, url, mode='track'):
        r = requests.get(url)
        html = r.content.decode('utf8')
        pattern = r'https://api\.soundcloud\.com/%s/(\d+)' % mode
        id = re.search(pattern, html).group(1)
        return id

    def get_track_ids_in_playlist(self, playlist_url):
        html = requests.get(playlist_url).content.decode('utf8')
        pattern = r'\"id\":(\d{6,12})'
        ids = set(re.findall(pattern, html))
        return ids

    def get_track_info(self, track_id):
        url = "https://api-v2.soundcloud.com/tracks/" + str(track_id)
        track = requests.get(url, {
            'client_id': self.client_id
        }).json()
        if not track:
            return None
        info = {
            'title': track['title'],
            'artist': track['user']['username'],
            'artwork_url': track['artwork_url'],
        }
        transcodings = track['media']['transcodings']
        for transcoding in transcodings:
            if transcoding['url'].endswith('progressive'):
                info['stream_url'] = transcoding['url']
                break
        return info

    def get_download_url(self, stream_url):
        response = requests.get(stream_url, {
            'client_id': self.client_id
        }).json()
        return response['url']

    def get_artwork(self, artwork_url):
        return requests.get(artwork_url).content

    def add_mp3_tags(self, track_path, track_info):
        mp3 = eyed3.load(track_path)
        if not mp3.tag:
            mp3.initTag()
        mp3.tag.title = track_info['title']
        mp3.tag.artist = track_info['artist']
        mp3.tag.album = track_info['title']
        if track_info['artwork_url']:
            img = self.get_artwork(track_info['artwork_url'].replace('large', 't500x500'))
            mp3.tag.images.set(3, img, "image/jpeg" ,u"SoundCloud")
        mp3.tag.save()

    def download_track_by_id(self, track_id):
        track_info = self.get_track_info(track_id)
        if not track_info:
            return
        track_name = os.path.join(track_info['title'] + '.mp3').replace('/', '')
        download_url = self.get_download_url(track_info['stream_url'])
        response = requests.get(download_url)
        track_path = os.path.join(self.save_dir, track_name)
        try:
            with open(track_path, 'wb') as f:
                f.write(response.content)
        except Exception as e:
            print(e)
        self.add_mp3_tags(track_path, track_info)
        print("Downloaded " + track_info['title'])

    def download_track_by_url(self, track_url):
        track_id = self.convert_url_to_id(track_url)
        self.download_track_by_id(track_id)

    def download_playlist_by_url(self, playlist_url):
        track_ids = self.get_track_ids_in_playlist(playlist_url)
        print("Found {0} tracks in playlist".format(len(track_ids)))
        with Pool(8) as p:
            p.map(self.download_track_by_id, track_ids)

    def download(self, url):
        url_info = self.detect_url(url)
        if not url_info:
            print("Cannot parse URL")
            return
        print("Downloading {0} {1} from {2}".format(url_info['type'], url_info['name'], url))
        if url_info['type'] == 'track':
            self.download_track_by_url(url)
        elif url_info['type'] == 'playlists':
            self.download_playlist_by_url(url)
        
def load_config():
    with open(CONFIG_PATH, 'r') as f:
        configs = json.load(f)
    return configs

if __name__ == '__main__':
    configs = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str, help="Download URL")
    parser.add_argument('-d', '--dir', action='store', default=configs['default_save_dir'],help="Save tracks location")
    parser.add_argument('--client-id', action='store', default=configs['client_id'], help="Client ID of SoundCloud user")
    args = parser.parse_args()
    client = SoundCloudClient(args.client_id, args.dir)
    client.download(args.url)
