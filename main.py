import os
import subprocess
import pygame
import vdf
import textwrap
import psutil
import time
import requests
from PIL import Image, ImageDraw, ImageFont

# Initialize Pygame and controller
pygame.init()
pygame.joystick.init()
joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
for joystick in joysticks:
    joystick.init()

# Get information about the current display
infoObject = pygame.display.Info()

# Set up the display in fullscreen mode
screen = pygame.display.set_mode((infoObject.current_w, infoObject.current_h), pygame.FULLSCREEN)
pygame.display.set_caption("Steam Game Launcher")

# Constants for layout (adjust based on screen size)
POSTER_WIDTH = int(infoObject.current_w * 0.1)  # 10% of screen width
POSTER_HEIGHT = int(POSTER_WIDTH * 1.5)  # 3:2 aspect ratio
MARGIN = int(infoObject.current_w * 0.02)  # 2% of screen width
GAMES_PER_ROW = (infoObject.current_w - MARGIN) // (POSTER_WIDTH + MARGIN)

# Function to render wrapped text
def render_wrapped_text(text, font, max_width, max_height, color):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        if font.size(test_line)[0] <= max_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    lines.append(' '.join(current_line))

    rendered_lines = []
    for line in lines:
        rendered_lines.append(font.render(line, True, color))

    total_height = sum(line.get_height() for line in rendered_lines)
    scale = min(1, max_height / total_height)

    scaled_lines = [pygame.transform.scale(line, (int(line.get_width() * scale), int(line.get_height() * scale))) for line in rendered_lines]

    return scaled_lines

# Function to fetch and resize Steam game posters
# TODO Center text on the image if no header image is found
def fetch_and_resize_poster(game_id, game_name, save_directory='/home/default/.local/share/posters'):
    # Create the directory if it doesn't exist
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)
    
    # Check if the image already exists to avoid overwriting
    if not os.path.exists(os.path.join(save_directory, f'{game_id}.png')):
        # Create a blank image with black background
        image = Image.new('RGB', (600, 800), 'black')
        draw = ImageDraw.Draw(image)

        # Define the font and text size
        # Draw a Title to show that it is steam-headless managed
        font = ImageFont.truetype("arial.ttf", 40)
        draw.text((150, 20), "Steam Headless", fill='white', font=font)

        # Draw tha game name at the footer
        text_width = draw.textlength(str(game_name), font=font)
        name_x_offset = (image.width - text_width) / 2

        # Draw the text with wrapping if necessary
        lines = []
        words = game_name.split(' ')
        line = ''
        for word in words:
            test_line = line + word + ' '
            test_width = draw.textlength(test_line, font=font)
            if test_width <= image.width:
                line = test_line
            else:
                lines.append(line)
                line = word + ' '
        lines.append(line)

        # Calculate the y-coordinate for each line of text
        name_y_offset = 600  # Starting y-coordinate
        for i, line in enumerate(lines):
            name_x_offset = (image.width - draw.textlength(str(line), font=font)) / 2
            draw.text((name_x_offset, name_y_offset), line, fill='white', font=font)
            name_y_offset += 40

        # Fetch the game poster from Steam API
        url = f'https://store.steampowered.com/api/appdetails?appids={game_id}'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if str(game_id) in data and data[str(game_id)]['success']:
                poster_url = data[str(game_id)]['data']['header_image']

                response_poster = requests.get(poster_url)
                if response_poster.status_code == 200:
                    # Open the fetched image and resize it to fit
                    poster_image = Image.open(requests.get(poster_url, stream=True).raw)
                    height = int((600 / poster_image.width) * poster_image.height)
                    resized_poster = poster_image.resize((600, height))
                    
                    # Calculate the position to center the image on the main image
                    x_offset = 0
                    y_offset = (800 - height) // 2
                    
                    # Paste the resized poster onto the black background
                    image.paste(resized_poster, (x_offset, y_offset))
                
        # Save the final image appid.png
        image.save(f'{save_directory}/{game_id}.png')

def get_steam_games():
    steam_path = os.path.expanduser("~/.steam/steam")
    library_folders_path = os.path.join(steam_path, "steamapps/libraryfolders.vdf")
    
    with open(library_folders_path, "r") as f:
        library_folders = vdf.load(f)
    
    games = []
    filtered_keywords = ["steam", "proton"]
    poster_dir = os.path.expanduser("~/.local/share/posters")
    
    for folder in library_folders["libraryfolders"].values():
        apps_path = os.path.join(folder["path"], "steamapps")
        for filename in os.listdir(apps_path):
            if filename.startswith("appmanifest_") and filename.endswith(".acf"):
                with open(os.path.join(apps_path, filename), "r") as f:
                    manifest = vdf.load(f)
                    game_info = manifest["AppState"]
                    game_name = game_info["name"]
                    appid = game_info["appid"]
                    
                    # Check if the game name contains any of the filtered keywords
                    if not any(keyword in game_name.lower() for keyword in filtered_keywords):
                        #fetch_and_resize_poster(appid, game_name)
                        games.append({
                            "name": game_name,
                            "appid": appid,
                            "poster_path": os.path.join(poster_dir, f"{appid}.png")
                        })
    return games

def launch_game(appid):
    try:
        # Launch the game using Steam's URL protocol
        process = subprocess.Popen(["steam", f"steam://rungameid/{appid}"])
        # Exit the Pygame script
        pygame.quit()
        
        # time.sleep(10)
        
        # steam_process = psutil.Process(process.pid)
        
        # while True:
        #     if not steam_process.is_running() or steam_process.status() == psutil.STATUS_ZOMBIE:
        #         break
            
        #     # Check if any child process is the game
        #     children = steam_process.children(recursive=True)
        #     if not any(child.name().lower() != "steam" for child in children):
        #         break
            
        #     time.sleep(1)
        
        # for child in steam_process.children(recursive=True):
        #     child.terminate()
        # steam_process.terminate()
        
        # print("Game has exited")
        
        
    except Exception as e:
        print(f"Error launching: {e}")


# Get installed games
games = get_steam_games()

# Main game loop
running = True
selected_game = 0
scroll_offset = 0
scroll_speed = 50 

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.JOYBUTTONDOWN:
            if event.button == 0:  # A button
                launch_game(sorted_games[selected_game]["appid"])
            elif event.button == 5:  # R1 button (scroll down)
                max_scroll = max(0, total_rows * (POSTER_HEIGHT + MARGIN) - screen.get_height())
                scroll_offset = min(max_scroll, scroll_offset + scroll_speed)
            elif event.button == 4:  # R2 button (scroll up)
                scroll_offset = max(0, scroll_offset - scroll_speed)
        elif event.type == pygame.JOYHATMOTION:
            if event.value[0] == -1:  # Left on D-pad
                selected_game = (selected_game - 1) % len(games)
            elif event.value[0] == 1:  # Right on D-pad
                selected_game = (selected_game + 1) % len(games)
            elif event.value[1] == 1:  # Up on D-pad
                selected_game = (selected_game - GAMES_PER_ROW) % len(games)
            elif event.value[1] == -1:  # Down on D-pad
                selected_game = (selected_game + GAMES_PER_ROW) % len(games)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:  # Esc key
                running = False
            elif event.key == pygame.K_LEFT:
                selected_game = (selected_game - 1) % len(games)
            elif event.key == pygame.K_RIGHT:
                selected_game = (selected_game + 1) % len(games)
            elif event.key == pygame.K_UP:
                selected_game = (selected_game - GAMES_PER_ROW) % len(games)
            elif event.key == pygame.K_DOWN:
                selected_game = (selected_game + GAMES_PER_ROW) % len(games)
            elif event.key == pygame.K_RETURN:
                launch_game(sorted_games[selected_game]["appid"])
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:  # Scroll up
                scroll_offset = max(0, scroll_offset - scroll_speed)
            elif event.button == 5:  # Scroll down
                max_scroll = max(0, total_rows * (POSTER_HEIGHT + MARGIN) - screen.get_height())
                scroll_offset = min(max_scroll, scroll_offset + scroll_speed)

    # Clear the screen
    screen.fill((0, 0, 0))

    # Calculate total rows and visible rows
    total_rows = (len(games) - 1) // GAMES_PER_ROW + 1
    visible_rows = (screen.get_height() - MARGIN) // (POSTER_HEIGHT + MARGIN)

    # Sort games alphabetically by name
    sorted_games = sorted(games, key=lambda x: x['name'].lower())

    # Display game posters in a grid
    for i, game in enumerate(sorted_games):
        row = i // GAMES_PER_ROW
        col = i % GAMES_PER_ROW
        x = col * (POSTER_WIDTH + MARGIN) + MARGIN
        y = (row * (POSTER_HEIGHT + MARGIN) + MARGIN) - scroll_offset

        if -POSTER_HEIGHT <= y < screen.get_height():
            # Draw background for the game tile
            pygame.draw.rect(screen, (50, 50, 50), (x, y, POSTER_WIDTH, POSTER_HEIGHT))

            # Draw a white border around the selected game poster
            if i == selected_game:
                border_rect = pygame.Rect(x - 2, y - 2, POSTER_WIDTH + 4, POSTER_HEIGHT + 4)
                pygame.draw.rect(screen, (169, 169, 169), border_rect)

            try:
                poster = pygame.image.load(game["poster_path"])
                poster = pygame.transform.scale(poster, (POSTER_WIDTH, POSTER_HEIGHT))
                screen.blit(poster, (x, y))
            except:
                font = pygame.font.Font(None, 24)
                text_lines = render_wrapped_text(game["name"], font, POSTER_WIDTH - 10, POSTER_HEIGHT - 10, (255, 255, 255))
                
                text_y = y + (POSTER_HEIGHT - sum(line.get_height() for line in text_lines)) // 2
                for line in text_lines:
                    text_x = x + (POSTER_WIDTH - line.get_width()) // 2
                    screen.blit(line, (text_x, text_y))
                    text_y += line.get_height()

    # Scrolling logic for keyboard and controller
    selected_row = selected_game // GAMES_PER_ROW
    if selected_row < scroll_offset // (POSTER_HEIGHT + MARGIN):
        scroll_offset = selected_row * (POSTER_HEIGHT + MARGIN)
    elif selected_row >= (scroll_offset + screen.get_height()) // (POSTER_HEIGHT + MARGIN):
        scroll_offset = (selected_row + 1) * (POSTER_HEIGHT + MARGIN) - screen.get_height()

    # Update the display
    pygame.display.flip()

pygame.quit()