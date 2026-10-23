import curses
import json
import locale
import shutil
import subprocess
import sys


try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass


def search_videos(query):
    result = subprocess.run(
        [
            "yt-dlp",
            "--dump-json",
            "--flat-playlist",
            "--playlist-end", "20",
            "--no-warnings",
            f"ytsearch20:{query}"
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    videos = []

    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
            video_id = item.get("id")

            if video_id:
                videos.append({
                    "title": item.get("title") or "Без названия",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "id": video_id,
                    "duration": item.get("duration")
                })
        except json.JSONDecodeError:
            continue

    return videos, result.stderr.strip()


def format_duration(value):
    if not isinstance(value, (int, float)):
        return ""

    value = int(value)
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes}:{seconds:02}"


def terminal_video_mode():
    result = subprocess.run(
        ["mpv", "--vo=help"],
        capture_output=True,
        text=True,
        errors="replace"
    )
    output = result.stdout + result.stderr
    available = set()

    for name in ("tct", "caca", "drm"):
        if name in output:
            available.add(name)

    if sys.stdin.isatty() and sys.stdout.isatty():
        if "tct" in available:
            return ["--vo=tct", "--profile=sw-fast", "--really-quiet"]
        if "caca" in available:
            return ["--vo=caca", "--really-quiet"]
        if "drm" in available:
            return ["--vo=drm", "--profile=sw-fast"]

    if "tct" in available:
        return ["--vo=tct", "--profile=sw-fast", "--really-quiet"]

    if "caca" in available:
        return ["--vo=caca", "--really-quiet"]

    if "drm" in available and sys.stdin.isatty() and sys.stdout.isatty():
        return ["--vo=drm", "--profile=sw-fast"]

    return None


def play_video(video, stdscr):
    video_args = terminal_video_mode()

    if video_args is None:
        curses.endwin()
        print("В этой сборке mpv нет подходящего видеовывода для терминала.")
        print("Проверь доступные режимы командой: mpv --vo=help")
        print("Нужен tct или caca для видео символами, либо drm для Linux TTY.")
        input("Нажми Enter, чтобы вернуться...")
        return

    curses.def_prog_mode()
    curses.endwin()

    command = [
        "mpv",
        *video_args,
        "--hwdec=no",
        "--ytdl-format=bestvideo*+bestaudio/best",
        "--",
        video["url"]
    ]

    try:
        subprocess.run(command, check=False)
    finally:
        try:
            curses.reset_prog_mode()
            stdscr.clear()
            stdscr.keypad(True)
            curses.curs_set(1)
            stdscr.refresh()
        except curses.error:
            pass


def draw(stdscr, query, videos, selected, message, searching=False):
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    def put(y, x, text, attr=0):
        if 0 <= y < height and x < width:
            try:
                stdscr.addnstr(y, x, str(text), max(0, width - x - 1), attr)
            except curses.error:
                pass

    put(1, 2, "YTTERM", curses.A_BOLD)
    put(2, 2, "YouTube в терминале")
    put(4, 2, "Поиск: " + query)
    put(5, 2, "-" * max(1, width - 4))

    available = max(0, height - 10)
    start = max(0, selected - available + 1) if available else 0

    for index in range(start, min(len(videos), start + available)):
        video = videos[index]
        title = video["title"]
        duration = format_duration(video.get("duration"))

        if duration:
            title = f"{title}  [{duration}]"

        attr = curses.A_REVERSE if index == selected else 0
        prefix = "> " if index == selected else "  "
        put(7 + index - start, 2, prefix + title, attr)

    if searching:
        message = "Ищу видео..."

    put(height - 3, 2, message)
    put(height - 2, 2, "Enter: поиск/просмотр | ↑↓: выбор | Backspace: удалить | Esc: очистить")
    stdscr.refresh()


def main(stdscr):
    stdscr.keypad(True)

    try:
        curses.curs_set(1)
    except curses.error:
        pass

    query = ""
    videos = []
    selected = 0
    message = "Введи запрос на русском или английском и нажми Enter"

    while True:
        draw(stdscr, query, videos, selected, message)
        key = stdscr.get_wch()

        if isinstance(key, str):
            if key == "\x1b":
                if query:
                    query = ""
                    videos = []
                    selected = 0
                    message = "Введи запрос и нажми Enter"
                else:
                    break
                continue

            if key in ("\n", "\r"):
                if videos:
                    play_video(videos[selected], stdscr)
                    message = "Воспроизведение завершено"
                elif query.strip():
                    message = "Ищу видео..."
                    draw(stdscr, query, videos, selected, message, True)
                    videos, error = search_videos(query.strip())
                    selected = 0

                    if videos:
                        message = f"Найдено видео: {len(videos)}. Нажми Enter для просмотра."
                    elif error:
                        message = "Не удалось найти видео. Проверь интернет и yt-dlp."
                    else:
                        message = "Ничего не найдено."
                else:
                    message = "Сначала введи поисковый запрос"
                continue

            if key in ("\x7f", "\b"):
                query = query[:-1]
                videos = []
                selected = 0
                message = "Введи запрос и нажми Enter"
                continue

            if key.isprintable():
                query += key
                videos = []
                selected = 0
                message = "Нажми Enter для поиска"
                continue

        elif key == curses.KEY_UP and videos:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN and videos:
            selected = min(len(videos) - 1, selected + 1)
        elif key == curses.KEY_BACKSPACE:
            query = query[:-1]
            videos = []
            selected = 0
            message = "Введи запрос и нажми Enter"


if __name__ == "__main__":
    missing = [name for name in ("yt-dlp", "mpv") if not shutil.which(name)]

    if missing:
        print("Не найдены программы: " + ", ".join(missing))
        print("Запусти в NixOS: nix-shell -p python3 yt-dlp mpv ffmpeg")
        sys.exit(1)

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
