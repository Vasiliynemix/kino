import cherrypy
from django.core.wsgi import get_wsgi_application
from cherrypy.lib.static import serve_file
import os
import django

from pkg.log import CustomLogger

CustomLogger().init_logging()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webapp_site.settings')
django.setup()

application = get_wsgi_application()


class Root:
    pass


if __name__ == '__main__':
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(BASE_DIR, 'static')

    cherrypy.config.update({
        'server.socket_host': '127.0.0.1',
        'server.socket_port': 8081,
        'engine.autoreload.on': False,
    })

    cherrypy.tree.mount(Root(), '/')

    # Обслуживание статических файлов
    cherrypy.tree.mount(None, '/static', {'/': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': STATIC_DIR,
        'tools.staticdir.index': 'index.html',
    }})

    cherrypy.tree.graft(application, '/')
    cherrypy.engine.start()
    cherrypy.engine.block()