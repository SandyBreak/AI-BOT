# -*- coding: UTF-8 -*-
import logging
import base64

from aiogram.types import Message, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram import Router, Bot

from openai import AsyncOpenAI

from admin.admin_logs import send_log_message

from models.emojis import Emojis

from services.postgres.role_management_service import RoleManagmentService
from services.postgres.user_service import UserService

from exceptions.errors import UserNotRegError, AccessDeniedError

router = Router()


@router.message(Command(commands=['img']))
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
    if (delete_message_id := (await state.get_data()).get('message_id')): await bot.delete_message(chat_id=message.chat.id, message_id=delete_message_id)
    await state.clear()
    message_log = False
    delete_message = False
    try:
        await UserService.check_user_rights(message.from_user.id)
        
        openai_api_key = await UserService.get_user_data(message.from_user.id, 'encrypted_api_account_key')
        
        temporary_user_data = await RoleManagmentService.get_temporary_user_data(message.from_user.id, 'all')
        
        load_message = await message.answer(f'{Emojis.TIME} Генерация изображения...')
        query_text = message.text[len('/img '):].strip()
        
        if query_text:
            try:
                client = AsyncOpenAI(api_key=openai_api_key, base_url="https://api.proxyapi.ru/openai/v1")
                response = await client.images.generate(
                    model=temporary_user_data.img_model,
                    prompt=query_text,
                    n=1,  # Количество изображений для генерации
                    size=temporary_user_data.quality_generated_image,  # Размер изображения
                    style='vivid',
                    response_format='b64_json'
                )
                await bot.delete_message(chat_id=message.chat.id, message_id=load_message.message_id)
                photo_file_path = f'downloads/generated_image{message.from_user.id}.png'
                with open(photo_file_path, 'wb') as photo_file:
                    photo_file.write(base64.b64decode(response.data[0].b64_json))
                photo = FSInputFile(photo_file_path)
                message_log = await bot.send_photo(chat_id=message.chat.id, photo=photo, caption=f"Вы запросили изображение по запросу: {query_text}")
            except Exception as e:
                message_log = await message.answer("Извините, произошла ошибка.")
                logging.error(f"Ошибка при генерации изображения у пользователя {message.from_user.id}: {e}")
        else:
            message_log = await message.reply("Пожалуйста, введите текст запроса после команды /img.")
    except UserNotRegError:
        delete_message = await message.answer(f"{Emojis.ALLERT} Вы не зарегистрированы! {Emojis.ALLERT}\nДля регистрации введите команду /start", reply_markup=ReplyKeyboardRemove())
    except AccessDeniedError:
        delete_message = await message.answer("Админстратор не дал вам доступ. Подождите пока вам придет уведомление о том что доступ разрешен", reply_markup=ReplyKeyboardRemove())
    if delete_message: await state.update_data(message_id=delete_message.message_id)
    
    if message_log: await send_log_message(message, bot, message_log)
    
    