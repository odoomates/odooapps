# The videos of Odoo Mates on YouTube, the Odoo 17 development playlist: made
# for Odoo 17, most of it is the same in Odoo 18, 19 and 20. The home screen
# lists them all, and a step links to the ones that explain what it builds.
PLAYLIST = 'PLqRRLx0cl0hq0T4SV-BHhCicWOpzyWcHd'
PLAYLIST_URL = 'https://www.youtube.com/playlist?list=%s' % PLAYLIST

# (id, title, length), in the order of the playlist
VIDEOS = [
    ('kxbPgOLkNxw', "How to create a module", '49:32'),
    ('ayUbfklMY9U', "Creating views and tracking", '40:53'),
    ('lN6XY79zfl4', "Sequence, noupdate, rec name and the create method", '36:05'),
    ('1sgflzCAx9U', "Status bar, buttons, conditional invisible and self", '28:20'),
    ('OOz37QIFvDw', "Many2many field, menu and app icons, handle widget, editable lists", '31:59'),
    ('7RzR6L1n_GU', "One2many fields", '17:31'),
    ('UpmnBT-pNEE', "Notebook and pages", '4:32'),
    ('VaTbYbUCQ-o', "Name search: search on several fields", '4:03'),
    ('5ga7dlVoZ2M', "Compute the display name", '5:55'),
    ('MmBFfqBevLI', "Computed fields, stored and not stored", '13:35'),
    ('QUnMKyhnXrY', "Related fields", '5:49'),
    ('sEQXJ_JHyMg', "Install Odoo on an Ubuntu server", '28:15'),
    ('ISiK8ylFrlw', "On delete: restrict, cascade and set null", '9:06'),
    ('rPcNU8sYF_M', "Inherit the delete method (unlink)", '3:15'),
    ('JXXuCaD-foY', "ValidationError and UserError: warn the users", '6:14'),
    ('Tj3EEYALJz8', "The ondelete decorator", '2:49'),
    ('rEL--QLXhMA', "Security: groups, access rights and record rules", '41:36'),
    ('9KWuFFd7tEw', "Webhooks: send and receive data", '20:20'),
    ('D3urHJ9rB2o', "Create a record with a webhook", '11:34'),
    ('NCBDO3LKcCU', "Call an existing menu action in your module", '8:37'),
    ('HiCtg7O1aP4', "Inheritance: add or remove fields of Odoo's modules", '22:31'),
    ('H5m1ShlK_7E', "Required, readonly and invisible", '13:17'),
    ('DThqZnWZJ38', "Search view and search panel: filters and group by", '29:21'),
]
# the first videos of the Odoo 16 playlist: Odoo on your own computer, before Code it
SETUP_PLAYLIST = 'PLqRRLx0cl0hpu9zH6o8gq6ORBoW5xMtA-'
SETUP_PLAYLIST_URL = 'https://www.youtube.com/playlist?list=%s' % SETUP_PLAYLIST
SETUP_VIDEOS = [
    ('r6YLxj3H5xc', "Install and configure Odoo with PyCharm", '28:33'),
    ('zKOAvDw-Lrk', "Configure a custom addons path", '3:52'),
    ('IeJFxmCG2Qs', "Create a module: models, menus, actions and views", '51:49'),
]
VIDEOS_BY_ID = {video[0]: video for video in VIDEOS}
SETUP_BY_ID = {video[0]: video for video in SETUP_VIDEOS}

# the videos of a step: {(course key or family, step key): [video ids]}
STEP_VIDEOS = {
    ('first_app', 'skeleton'): ['kxbPgOLkNxw'],
    ('first_app', 'model'): ['kxbPgOLkNxw'],
    ('first_app', 'access'): ['rEL--QLXhMA'],
    ('first_app', 'menu'): ['kxbPgOLkNxw', 'OOz37QIFvDw'],
    ('first_app', 'form'): ['ayUbfklMY9U', 'UpmnBT-pNEE'],
    ('first_app', 'list_search'): ['DThqZnWZJ38'],
    ('first_app', 'authors'): ['7RzR6L1n_GU', 'ISiK8ylFrlw'],
    ('first_app', 'buttons'): ['1sgflzCAx9U'],
    ('first_app', 'compute'): ['MmBFfqBevLI'],
    ('first_app', 'conditions'): ['H5m1ShlK_7E'],
    ('first_app', 'chatter'): ['ayUbfklMY9U'],
    ('first_app', 'tracking'): ['ayUbfklMY9U'],
    ('contacts', 'inherit'): ['HiCtg7O1aP4'],
    ('contacts', 'form'): ['HiCtg7O1aP4'],
    ('contacts', 'list_search'): ['DThqZnWZJ38'],
    ('contacts', 'compute'): ['MmBFfqBevLI'],
    ('kanban', 'app'): ['OOz37QIFvDw'],
    ('kanban', 'stages'): ['lN6XY79zfl4'],
    ('kanban', 'link'): ['1sgflzCAx9U'],
    ('security', 'groups'): ['rEL--QLXhMA'],
    ('security', 'access'): ['rEL--QLXhMA'],
    ('security', 'own'): ['rEL--QLXhMA'],
    ('security', 'menus'): ['rEL--QLXhMA'],
    ('security', 'fields'): ['rEL--QLXhMA'],
}


def video(video_id):
    playlist = SETUP_PLAYLIST if video_id in SETUP_BY_ID else PLAYLIST
    video_id, title, length = SETUP_BY_ID.get(video_id) or VIDEOS_BY_ID[video_id]
    return {'id': video_id, 'title': title, 'length': length,
            'url': 'https://www.youtube.com/watch?v=%s&list=%s' % (video_id, playlist),
            'thumbnail': 'https://i.ytimg.com/vi/%s/mqdefault.jpg' % video_id}


def videos():
    return [dict(video(video_id), number=number) for number, (video_id, _title, _length) in enumerate(VIDEOS, 1)]


def setup_videos():
    return [dict(video(video_id), number=number) for number, (video_id, _title, _length) in enumerate(SETUP_VIDEOS, 1)]


def step_videos(course, step_key):
    ids = STEP_VIDEOS.get((course['key'], step_key)) or STEP_VIDEOS.get((course.get('family'), step_key)) or []
    return [video(video_id) for video_id in ids]
