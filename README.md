# mq-yt-dlp

copy the target URL, yt-dlp will automatically start the download

## Run

### WSL
```
brew install deno yt-dlp
docker compose up -d
```

#### yt-dlp configuration

this is an example: in ~/.config/yt-dlp/config

```
--js-runtimes deno:/home/linuxbrew/.linuxbrew/bin/deno
-f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
-o ~/Downloads/%(title)s.%(ext)s
```

### Windows
```
git clone https://github.com/sharl/mq-yt-dlp.git
cd mq-yt-dlp
pip install -r requirements.txt
python mq-yt-dlp.py
```

#### Settings

saved in `url_settings.json`
