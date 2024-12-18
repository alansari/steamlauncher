import os
import vdf
import sqlite3
from sqlmodel import create_engine, SQLModel, Field, Session, select
import pygame
import subprocess
import requests
import warnings
from PIL import Image, ImageOps
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

# Define the Game model for SQLModel
class Game(SQLModel, table=True):
    app_id: int = Field(default=None, primary_key=True)
    name: str
    install_path: str
    is_favorite: bool = False
    poster_path: str = ''  # Default to an empty string

# Database setup
sqlite_file_name = "games.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url)

SQLModel.metadata.create_all(engine)

# Suppress the libpng warning about incorrect sRGB profile
warnings.filterwarnings("ignore", category=UserWarning, message=".*known incorrect sRGB profile.*")

def scan_steam_games():
    vdf_path = os.path.expanduser("~/.steam/steam/steamapps/libraryfolders.vdf")
    
    if not os.path.exists(vdf_path):
        print("Steam library file not found!")
        return

    with open(vdf_path, 'r') as f:
        data = vdf.load(f)

    games = {}
    for lib in data['libraryfolders'].values():
        appmanifest_files = [f for f in os.listdir(lib['path'] + '/steamapps/') if f.startswith('appmanifest_')]
        for file in appmanifest_files:
            manifest_path = os.path.join(lib['path'], 'steamapps', file)
            with open(manifest_path, 'r') as mf:
                manifest_data = vdf.load(mf)

            # Extract the app_id from the AppState section
            try:
                app_id = int(manifest_data['AppState']['appid'])
            except (KeyError, ValueError) as e:
                print(f"Failed to extract app_id from {file}: {e}")
                continue

            game_name = manifest_data['AppState'].get('name')
            install_path = manifest_data['AppState'].get('installdir', '')
            parent_app_id = manifest_data['AppState'].get('parentappid')

            # Skip entries with "proton" or "runtime" in the name
            if not game_name or 'proton' in game_name.lower() or 'runtime' in game_name.lower():
                continue

            if parent_app_id:
                try:
                    parent_app_id = int(parent_app_id)
                    # Use the parent app_id as the key
                    games[parent_app_id] = {
                        'name': game_name,
                        'install_path': install_path
                    }
                except ValueError as e:
                    print(f"Failed to convert parentappid from {file}: {e}")
            else:
                # Use the current app_id as the key
                games[app_id] = {
                    'name': game_name,
                    'install_path': install_path
                }

    return games

def fetch_and_resize_poster(game_id, game_name, save_directory='./posters', session: Session = None):
    # Create the directory if it doesn't exist
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    poster_path = os.path.join(save_directory, f'{game_id}.png')

    # Check if the image already exists to avoid overwriting
    if not os.path.exists(poster_path):
        # Fetch the game poster from Steam API
        url = f'https://store.steampowered.com/api/appdetails?appids={game_id}'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if str(game_id) in data and data[str(game_id)]['success']:
                poster_url = data[str(game_id)]['data'].get('header_image')
                if poster_url:
                    img_response = requests.get(poster_url)
                    if img_response.status_code == 200:
                        try:
                            img = Image.open(BytesIO(img_response.content))

                            img = img.resize((150, 70), Image.Resampling.LANCZOS)

                            # Save the image as appid.png
                            img.save(poster_path)

                            # Update the poster_path in the database
                            if session:
                                game = session.get(Game, game_id)
                                if game:
                                    game.poster_path = poster_path
                                    session.add(game)
                                    session.commit()
                        except Exception as e:
                            print(f'Failed to process image from {poster_url}: {e}')
                    else:
                        print(f'Failed to fetch image from {poster_url}')
                else:
                    print(f"No header_image found for game ID: {game_id}")
            else:
                print(f'Failed to get data for game ID: {game_id} from Steam API')
        else:
            print(f'Failed to get data from Steam API for game ID: {game_id}')

    return poster_path

def save_games_to_db(games):
    with Session(engine) as session:
        for app_id, game_info in games.items():
            # Check if the game already exists in the database
            existing_game = session.get(Game, app_id)

            if existing_game:
                # Update the existing game record
                existing_game.name = game_info['name']
                existing_game.install_path = game_info['install_path']
            else:
                # Insert a new game record
                new_game = Game(app_id=app_id, name=game_info['name'], install_path=game_info['install_path'])
                session.add(new_game)

        session.commit()

def load_games_from_db(filter_favorites=False):
    with Session(engine) as session:
        if filter_favorites:
            statement = select(Game).where(Game.is_favorite == True).order_by(Game.name)
        else:
            statement = select(Game).order_by(Game.name)  # Sort by name alphabetically
        games = session.exec(statement).all()
        return games

def toggle_favorite(app_id):
    with Session(engine) as session:
        game = session.get(Game, app_id)
        if game:
            game.is_favorite = not game.is_favorite
            session.add(game)
            session.commit()

def launch_game(app_id):
    subprocess.Popen(["steam", f"steam://rungameid/{app_id}"])

def main():
    # Scan and save games to the database
    games = scan_steam_games()
    save_games_to_db(games)

    # Load games from the database
    games_list = load_games_from_db()
    pygame.init()

    # Load the star image
    try:
        star_image = pygame.image.load("./assets/star.png").convert_alpha()
        star_image = pygame.transform.scale(star_image, (30, 30)) 
    except Exception as e:
        print(f"Failed to load star image: {e}")
        star_image = None

    # Initialize joystick support
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joysticks connected")
    else:
        pygame.joystick.init()
        joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        for joystick in joysticks:
            joystick.init()
        joystick = pygame.joystick.Joystick(0)
        print(f"Using joystick: {joystick.get_name()}")

    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    font = pygame.font.Font(None, 36)
    small_font = pygame.font.Font(None, 24)
    clock = pygame.time.Clock()

    # Constants
    POSTER_HEIGHT = 100
    FOOTER_HEIGHT = 100
    SPACING_BETWEEN_ITEMS = 10

    # Calculate screen dimensions
    screen_width, screen_height = screen.get_size()

    # Calculate the available height for game entries
    available_height_for_games = screen_height - FOOTER_HEIGHT

    # Calculate items per page
    item_height = POSTER_HEIGHT + SPACING_BETWEEN_ITEMS
    items_per_page = available_height_for_games // item_height

    selected_index = 0
    visible_range_start = 0

    running = True
    filter_favorites = False

    # Use ThreadPoolExecutor for background image fetching
    executor = ThreadPoolExecutor(max_workers=5)

    # Dictionary to store future objects for posters
    poster_futures = {}

    def skip_to_next_letter(games_list, current_index):
        if not games_list:
            return 0
        current_initial = games_list[current_index].name[0].upper()
        next_initials = [game.name[0].upper() for game in games_list if game.name[0].upper() > current_initial]
        if not next_initials:
            return 0
        next_initial = min(next_initials)
        for i, game in enumerate(games_list):
            if game.name[0].upper() == next_initial:
                return i
        return 0
    
    def skip_to_previous_letter(games_list, current_index):
        if not games_list:
            return 0
        current_initial = games_list[current_index].name[0].upper()
        previous_initials = [game.name[0].upper() for game in games_list if game.name[0].upper() < current_initial]
        if not previous_initials:
            return 0
        previous_initial = max(previous_initials)
        for i, game in enumerate(games_list):
            if game.name[0].upper() == previous_initial:
                return i
        return 0

    # The legend
    legend_text = [
        "A: Launch Game | B: Exit | Y: Toggle Favorite",
        "Start: Toggle Favorites | L2/R2: Skip to Next Letter"
    ]

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_UP:
                    selected_index = (selected_index - 1) % len(games_list)
                    if selected_index < visible_range_start:
                        visible_range_start = max(0, selected_index)
                elif event.key == pygame.K_DOWN:
                    selected_index = (selected_index + 1) % len(games_list)
                    if selected_index >= visible_range_start + items_per_page:
                        visible_range_start = min(len(games_list) - items_per_page, selected_index - items_per_page + 1)
                elif event.key == pygame.K_PAGEUP:
                    selected_index = skip_to_previous_letter(games_list, selected_index)
                    visible_range_start = max(0, selected_index - items_per_page + 1)
                elif event.key == pygame.K_PAGEDOWN:
                    selected_index = skip_to_next_letter(games_list, selected_index)
                    visible_range_start = max(0, selected_index - items_per_page + 1)
                elif event.key == pygame.K_RETURN:
                    launch_game(games_list[selected_index].app_id)
                elif event.key == pygame.K_BACKSPACE:
                    filter_favorites = not filter_favorites
                    games_list = load_games_from_db(filter_favorites=filter_favorites)
                    selected_index = 0
                    visible_range_start = 0
                elif event.key == pygame.K_f:
                    toggle_favorite(games_list[selected_index].app_id)
            elif event.type == pygame.JOYBUTTONDOWN:
                if event.button == 3:  # Y button on Xbox controller (button index is 3)
                    toggle_favorite(games_list[selected_index].app_id)
                elif event.button == 7:  # Start button on Xbox controller (button index is 7)
                    filter_favorites = not filter_favorites
                    games_list = load_games_from_db(filter_favorites=filter_favorites)
                    selected_index = 0
                    visible_range_start = 0
                elif event.button == 0:  # A button on Xbox controller (button index is 0)
                    launch_game(games_list[selected_index].app_id)
                elif event.button == 1:  # B button on Xbox controller (button index is 1)
                    running = False
                elif event.button == 6:  # L2 button on Xbox controller (button index is 6)
                    selected_index = skip_to_next_letter(games_list, selected_index)
                    visible_range_start = max(0, selected_index - items_per_page + 1)
                elif event.button == 7:  # R2 button on Xbox controller (button index is 7)
                    selected_index = skip_to_next_letter(games_list, selected_index)
                    visible_range_start = max(0, selected_index - items_per_page + 1)
            elif event.type == pygame.JOYAXISMOTION:
                if event.axis == 1:  # Left thumbstick vertical axis (axis index is 1)
                    if event.value < -0.5:  # Up
                        selected_index = (selected_index - 1) % len(games_list)
                        if selected_index < visible_range_start:
                            visible_range_start = max(0, selected_index)
                    elif event.value > 0.5:  # Down
                        selected_index = (selected_index + 1) % len(games_list)
                        if selected_index >= visible_range_start + items_per_page:
                            visible_range_start = min(len(games_list) - items_per_page, selected_index - items_per_page + 1)
                elif event.axis == 0:  # Left thumbstick horizontal axis (axis index is 0)
                    pass  # You can add additional actions if needed

        screen.fill((0, 0, 0))
        
        visible_games = games_list[visible_range_start:visible_range_start + items_per_page]
        for i, game in enumerate(visible_games):
            color = (255, 255, 255) if (selected_index - visible_range_start == i) else (180, 180, 180)
            
            # Calculate vertical position based on item height and spacing
            y_offset = 40 + i * item_height
            
            # Display the game name
            text = font.render(game.name, True, color)
            screen.blit(text, (250, y_offset))  # Adjusted to make space for the star image
            
            # Load and display the poster if it exists
            if game.poster_path:
                try:
                    poster_image = pygame.image.load(game.poster_path).convert_alpha()
                    screen.blit(poster_image, (10, y_offset - 5))  # Adjusted to align with text better
                    
                    # Display the star image next to the poster if the game is a favorite
                    if game.is_favorite and star_image is not None:
                        # Get the dimensions of the poster image
                        poster_rect = poster_image.get_rect(topleft=(10, y_offset - 5))
                        # Calculate the position for the star image at the top-right corner of the poster
                        star_position = (poster_rect.topright[0] - star_image.get_width() + 5, poster_rect.topright[1] - 5)
                        screen.blit(star_image, star_position)
                except Exception as e:
                    print(f"Failed to load image {game.poster_path}: {e}")
            else:
                # If the poster is not yet loaded, fetch it in the background
                if game.app_id not in poster_futures:
                    with Session(engine) as session:
                        future = executor.submit(fetch_and_resize_poster, game.app_id, game.name, session=session)
                        poster_futures[game.app_id] = future
                elif poster_futures[game.app_id].done():
                    try:
                        poster_path = poster_futures[game.app_id].result()
                        if poster_path:
                            game.poster_path = poster_path
                    except Exception as e:
                        print(f"Error processing future for game ID {game.app_id}: {e}")
        
        # Display the legend at the bottom of the screen
        footer_y_offset = screen.get_height() - FOOTER_HEIGHT 
        for i, line in enumerate(legend_text):
            text = small_font.render(line, True, (255, 255, 255))
            screen.blit(text, (screen.get_width() // 2 - text.get_width() // 2, footer_y_offset + i * 30)) 
        
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
