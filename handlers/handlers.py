import os
from aiogram import types, Dispatcher
from create_bot import bot, ADMIN, USERS, OPENAI_TOKEN
from keyboards.keyboards import get_start_kb, get_cancel
from aiogram.dispatcher.storage import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from functools import wraps
import speech_recognition as sr
import requests
import io
import os
from pydub import AudioSegment

texts = {"help": "help"}


class UserStatesGroup(StatesGroup):
    add_user = State()


r = sr.Recognizer()


def admin(func):
    @wraps(func)
    async def wrapped(message: types.Message, *args, **kwargs):
        if message.from_user.id != ADMIN:
            return
        return await func(message, *args, **kwargs)

    return wrapped


async def get_users():
    global USERS
    with open('.env', 'r') as env_file:
        for line in env_file:
            if line.startswith('USERS_IDS'):
                USERS = line.split('=')[1].strip().split(',')
                USERS = {int(uid.split(':')[0]): uid.split(':')[1] for uid in USERS}
                break


async def help_command_client(message: types.Message) -> None:
    if message.from_user.id in USERS:
        await message.answer(texts['help'],
                             reply_markup=get_start_kb())


@admin
async def cancel_command(message: types.Message, state: FSMContext) -> None:
    if state is None:
        return
    await message.reply('Действие отменено!',
                        reply_markup=get_start_kb())

    await state.finish()


async def start_command(message: types.Message) -> None:
    if message.from_user.id in USERS:
        await message.answer(f"Привет, {message.from_user.first_name}!\n"
                             f"Пришли запрос для chatGPT",
                             reply_markup=get_start_kb())
    else:
        await message.answer(f"Здравствуй, {message.from_user.first_name}!\n"
                             f"Запрос на доступ к функционалу бота отправлен Администратору!\n"
                             f"Ожидай подтверждение!",
                             reply_markup=get_start_kb())

        await bot.send_message(ADMIN, text=f"Запрос на доступ:\n"
                                           f"Username: {message.from_user.username}\n"
                                           f"full_name: {message.from_user.full_name}\n")
        await bot.send_message(ADMIN, text=f"{message.from_user.id}:{message.from_user.last_name}")


@admin
async def add_user(message: types.Message):
    await message.reply("Для добавления отправь:\n"
                        "id:last_name",
                        reply_markup=get_cancel())
    await UserStatesGroup.add_user.set()


@admin
async def set_user(message: types.Message, state: FSMContext):
    with open('.env', 'r+') as env_file:
        env_lines = env_file.readlines()

        for i, line in enumerate(env_lines):
            if line.startswith('USERS_IDS'):

                users = line[len('USERS_IDS='):].strip().split(',')

                if message.text not in users:
                    users.append(message.text)

                env_lines[i] = f"USERS_IDS={','.join(users)}\n"
                env_file.seek(0)
                env_file.writelines(env_lines)
                env_file.truncate()
                await message.reply(f"Пользователь {message.text} успешно добавлен!",
                                    reply_markup=get_start_kb())
                await bot.send_message(message.text, f"Доспут открыт!\n"
                                                     f"Для начала работы нажми /start")
                await state.finish()
                await get_users(message)
                return
    await message.reply("Не удалось найти переменную USERS в файле .env.")


async def recognize_speech(audio_file: types.Audio):
    file_info = await bot.get_file(audio_file.file_id)
    file_path = file_info.file_path
    file_data = await bot.download_file(file_path)
    with io.BytesIO(file_data.read()) as f:
        with open('audio.oga', 'wb') as wav_file:
            wav_file.write(f.getvalue())
    wav_path = os.path.splitext('audio.oga')[0] + ".wav"
    AudioSegment.from_file('audio.oga').export(wav_path, format="wav")

    with sr.AudioFile(wav_path) as source:
        audio_data = r.record(source)

    text = r.recognize_google(audio_data, language='ru-RU')
    return text

async def voice_message_handler(message: types.Message):
    if message.from_user.id in USERS:
        voice = message.voice
        text = await recognize_speech(voice)
        print(text)
        answer = generate_text(text)
        print(answer)
        await message.reply(f'Запрос: {text}\n\n'
                            f'Ответ: {answer}')


def generate_text(prompt):
    url = 'https://api.openai.com/v1/engines/text-davinci-002/completions'
    headers = {'Authorization': f'Bearer {OPENAI_TOKEN}'}
    data = {
        'prompt': prompt,
        'max_tokens': 200,
        'temperature': 0.6,
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()['choices'][0]['text']


async def generate_handler(message: types.Message):
    if message.from_user.id in USERS:
        response = generate_text(message.text)
        await message.reply(response)


def register_handlers_client(dp: Dispatcher):
    dp.register_message_handler(help_command_client, commands=['help'])
    dp.register_message_handler(cancel_command, commands=['canсel'], state="*")
    dp.register_message_handler(start_command, commands=['start'])
    dp.register_message_handler(add_user, commands=['add_user'])
    dp.register_message_handler(get_users, commands=['get_users'])
    dp.register_message_handler(set_user, state=UserStatesGroup.add_user)
    dp.register_message_handler(voice_message_handler, content_types=types.ContentType.VOICE)
    dp.register_message_handler(generate_handler)