import bs4
import requests
import subprocess
import tempfile

from backend.backend import app, cache, cache_interval
from canteens.canteen import Canteen, VEGGIE, MEAT
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def __parse_menu():

    def get_dropbox_link():
        request = requests.get('http://cafenero.net/speisen.html')
        if request.status_code == requests.codes.ok:
            soup = bs4.BeautifulSoup(request.text, 'html.parser')
            iframe = soup.find('iframe')
            return iframe.attrs['src']
        else:
            return False

    def get_pdf():
        dropbox_link = get_dropbox_link()
        if dropbox_link:
            request = requests.get(dropbox_link)
            if request.status_code == requests.codes.ok:
                tmpdir = tempfile.mkdtemp()
                pdfpath = '%s/cafenero.pdf' % tmpdir
                with open(pdfpath, 'wb') as f:
                    f.write(request.content)
                return tmpdir
            else:
                return False
        else:
            return False

    def pdf_to_text(tmpdir):
        pdfpath = '%s/cafenero.pdf' % tmpdir
        txtpath = '%s/cafenero.txt' % tmpdir
        popen = subprocess.Popen(('pdftotext', '-layout', pdfpath), stdout=subprocess.PIPE)
        popen.wait()
        with open(txtpath, 'r') as f:
            menu = f.read()
        return menu

    def get_menu():
        def clean_newlines(text):
            cleaned_result = ''
            for line in text.splitlines():
                if not line == '' and 'cafeneroinder' not in line:
                    if 'mittagstisch' in line or '---' in line or 'schonkost' in line:
                        line = '%s\n' % line
                    else:
                        if line.endswith(('€', 'vegetarisch', 'schweinefleisch')):
                            line = '%s\n' % line
                        else:
                            line = '%s ' % line
                    cleaned_result += line
            return cleaned_result

        result = ''
        for entry in clean_newlines(pdf_to_text(get_pdf())).splitlines():
            if 'mittagstisch' in entry or '---' in entry or 'schonkost' in entry:
                annotation = ''
            elif 'vegetarisch' in entry:
                annotation = '%s ' % VEGGIE
            else:
                annotation = '%s ' % MEAT
            entry = entry.replace('vegetarisch', '')
            entry = entry.replace('schweinefleisch', '')
            entry = ' '.join(entry.split())
            result += '%s%s\n' % (annotation, entry)
        return result

    return get_menu()


@app.task(bind=True, default_retry_delay=30)
def update_cafenero(self):
    try:
        logger.info('[Update] TU Cafenero')
        menu = __parse_menu()
        if menu:
            cache.set('tu_cafenero', menu, ex=cache_interval * 4)
    except Exception as ex:
        raise self.retry(exc=ex)

if __name__ == '__main__':
    print(__parse_menu())