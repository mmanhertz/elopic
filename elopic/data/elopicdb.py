from operator import itemgetter
from os import path, listdir

from tinydb import Query
from tinydb import TinyDB
from tinydb.operations import increment

import settings
from elopic.logic.elo import INITIAL_ELO_SCORE

ELOPIC_DB_NAME = 'elopic.data'
ELOPIC_EXTENSIONS = ['.jpg', '.jpeg']


class EloPicDBError(Exception):
    pass


class EloPicDB:
    """
    Simple wrapper class for elopic's underlying database. Abstracts all data
    related functions so replacing TinyDB in the future would be easy.
    """
    def __init__(self):
        self._db = None
        self._dir = ''

    def load_from_disk(self, directory):
        """
        Reads the EloImages from `directory`.

        If an `elopic.data` file from a previous run exists in the directory,
        read from there (doing a consistency check for moved / added / deleted
        files).
        Otherwise read the images in the directory and create an initial
        `elopic.data`.
        :param directory: Filesystem path to the directory holding the image
        files.
        """
        assert path.isdir(directory)
        self._dir = path.abspath(directory)
        db_path = path.join(self._dir, ELOPIC_DB_NAME)
        try:
            self._db = TinyDB(db_path)
        except ValueError as err:
            err.message = 'Unable to read {}: {}\n'.format(db_path, err.message)
            raise
        try:
            self.validate()
        except Exception as err:
            err.message = 'Error while validating elopic.data in {}: {}'.format(
                self._dir, err.message
            )

    def validate(self):
        """
        Makes sure all the files in `self._dir` are present in self._db.

        Files that have been added to the directory are added to the data with
        initial values.
        """
        # TODO: Flag missing files instead of removing them from the data.
        # TODO: Use os.walk to find files recursively in subdirs.
        # TODO: Use hash values instead of filenames to distinguish images,
        #       possibly find similar / duplicate images
        # TODO: Files that are not (any longer) in the directory are removed
        #       from the data?
        for img in listdir(self._dir):
            if any(img.lower().endswith(ext) for ext in ELOPIC_EXTENSIONS):
                try:
                    self._validate_image(path.join(self._dir, img))
                except Exception as err:
                    err.message = 'Error while validating {}: {}'.format(
                        img, err.message
                    )

    def _validate_image(self, image_path):
        Image = Query()
        result = self._db.search(Image.path == image_path)
        if len(result) == 0:
            # Image not in DB yet -> add it
            self._db.insert({
                'path': image_path,
                'rating': INITIAL_ELO_SCORE,
                'seen_count': 0,
                'ignore': 0,
            })

        if len(result) > 1:
            # Image in DB more than once -> raise
            raise EloPicDBError(
                'Multiple entries for the same image: "{}".'.format(image_path)
            )

        # migration for old DB files: add 'seen_count' field, if it does not exist already
        if 'seen_count' not in result[0]:
            self._db.update({'seen_count': 0}, Image.path == image_path)

        # migration: add 'ignore' field
        if 'ignore' not in result[0]:
            self._db.update({'ignore': 0}, Image.path == image_path)

        # Image already in DB and now fully migrated.
        return

    def get_random_images(self, count):
        images = settings.STRATEGY(self.get_all(), count)
        return images

    def get_rating(self, image_path):
        Image = Query()
        image = self._db.get(Image.path == image_path)
        return image['rating']

    def update_rating(self, image_path, rating):
        Image = Query()
        self._db.update({'rating': rating}, Image.path == image_path)
        self._db.update(increment('seen_count'), Image.path == image_path)

    def to_list(self):
        return [[entry['path'], entry['seen_count'], entry['rating'], entry['ignore']] for entry in self._db.all()]

    def get_headers(self):
        return self._db.all()[0].keys()

    def get_top_x_filepaths_by_rating(self, x):
        all = self.get_all()
        top_x = sorted(all, key=itemgetter('rating'), reverse=True)[:x]
        top_x_paths = [item['path'] for item in top_x]
        return top_x_paths

    def ignore_pictures(self, images_to_ignore):
        Image = Query()
        for image_path in images_to_ignore:
            self._db.update({'ignore': 1}, Image.path == image_path)

    def get_all(self):
        Image = Query()
        return self._db.search(Image.ignore == 0)

    def close(self):
        self._db.close()