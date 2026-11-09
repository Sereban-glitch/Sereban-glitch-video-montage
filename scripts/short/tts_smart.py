#!/usr/bin/env python3
"""
tts_smart.py - Двуязычный синтезатор речи для Shorts & контент-завода.

Поддерживает:
- Языки: Украинский (uk), Русский (ru), Смешанный/Суржик (mixed), Автоопределение (auto).
- Разделение потоков: subtitle_text (чистый текст) и phonetic_text (с ударениями/заменами).
- Движки:
    * edge_smart (по умолчанию, нулевая нагрузка на CPU, умный fallback)
    * silero (локальный CPU с точным контролем ударений через '+')
    * clone_cloud (клон голоса через HuggingFace Space с авто-fallback)
- Студийная постобработка через FFmpeg (highpass + acompressor + loudnorm EBU R128).
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

# Регулярные выражения для маркеров языка
UK_MARKERS = re.compile(r"[іїєґІЇЄҐ]")
RU_MARKERS = re.compile(r"[ыэъёЫЭЪЁ]")

# Пути по умолчанию
DEFAULT_DICT_PATH = Path(__file__).resolve().parent / "custom_pronunciation.json"
DEFAULT_REF_VOICE = Path("/home/qwerty/.config/opencode/skills/video-montage/assets/my_voice_ref.wav")


class TTSSmart:
    def __init__(self, dict_path: Optional[Path] = None):
        self.dict_path = dict_path or DEFAULT_DICT_PATH
        self.pronunciation = self._load_dictionary()
        self._uk_stressifier = None
        self._ru_accentizer = None
        self._silero_models = {}

    def _load_dictionary(self) -> Dict[str, Dict[str, str]]:
        if self.dict_path.exists():
            try:
                data = json.loads(self.dict_path.read_text(encoding="utf-8"))
                return {
                    "common": data.get("common", {}),
                    "uk": data.get("uk", {}),
                    "ru": data.get("ru", {})
                }
            except Exception as e:
                print(f"[TTSSmart] Ошибка чтения словаря {self.dict_path}: {e}", file=sys.stderr)
        return {"common": {}, "uk": {}, "ru": {}}

    # -------------------------------------------------------------------------
    # 1. Разделение текста: Subtitles Text vs Phonetic Text
    # -------------------------------------------------------------------------
    @staticmethod
    def clean_subtitle_text(text: str) -> str:
        """Очищает текст от знаков ударения '+' и технических меток для субтитров."""
        cleaned = re.sub(r"\+([а-яА-Яa-zA-ZіІїЇєЄґҐ])", r"\1", text)
        cleaned = cleaned.replace("+", "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    # -------------------------------------------------------------------------
    # 2. Определение языка (Language Router)
    # -------------------------------------------------------------------------
    def detect_language(self, text: str, forced_lang: str = "auto") -> str:
        if forced_lang in ("uk", "ru", "mixed"):
            return forced_lang

        has_uk = bool(UK_MARKERS.search(text))
        has_ru = bool(RU_MARKERS.search(text))

        if has_uk and has_ru:
            return "mixed"
        if has_uk:
            return "uk"
        if has_ru:
            return "ru"

        # Fallback через langdetect если нет характерных графем
        try:
            from langdetect import detect
            code = detect(text)
            if code == "uk":
                return "uk"
            if code == "ru":
                return "ru"
        except Exception:
            pass

        return "ru"

    # -------------------------------------------------------------------------
    # 3. Препроцессинг ударений и фонетики (Bi-Lingual Stress Engine)
    # -------------------------------------------------------------------------
    def _apply_dict(self, text: str, mapping: Dict[str, str]) -> str:
        if not mapping:
            return text
        for key in sorted(mapping.keys(), key=len, reverse=True):
            pattern = rf"(?<![\w-]){re.escape(key)}(?![\w-])"
            text = re.sub(pattern, mapping[key], text, flags=re.IGNORECASE)
        return text

    def _get_uk_stressifier(self):
        if self._uk_stressifier is None:
            try:
                import ukrainian_word_stress
                self._uk_stressifier = ukrainian_word_stress.Stressifier()
            except Exception as e:
                print(f"[TTSSmart] Предупреждение: ukrainian-word-stress недоступен: {e}", file=sys.stderr)
        return self._uk_stressifier

    def _get_ru_accentizer(self):
        if self._ru_accentizer is None:
            try:
                from ruaccent import RUAccent
                acc = RUAccent()
                acc.load(omograph_model_size="tiny", use_dictionary=False, tiny_mode=True)
                self._ru_accentizer = acc
            except Exception as e:
                print(f"[TTSSmart] Предупреждение: ruaccent недоступен: {e}", file=sys.stderr)
        return self._ru_accentizer

    def preprocess_text(self, text: str, lang: str, engine: str = "edge_smart") -> Tuple[str, str]:
        """Возвращает кортеж (subtitle_text, phonetic_text)."""
        subtitle_text = self.clean_subtitle_text(text)
        phonetic_text = text

        # 1. Применяем словарь замен
        phonetic_text = self._apply_dict(phonetic_text, self.pronunciation.get("common", {}))
        if lang == "uk":
            phonetic_text = self._apply_dict(phonetic_text, self.pronunciation.get("uk", {}))
        elif lang == "ru":
            phonetic_text = self._apply_dict(phonetic_text, self.pronunciation.get("ru", {}))
        elif lang == "mixed":
            phonetic_text = self._apply_dict(phonetic_text, self.pronunciation.get("ru", {}))
            phonetic_text = self._apply_dict(phonetic_text, self.pronunciation.get("uk", {}))

        # 2. Обработка ударений в зависимости от движка
        if engine == "silero":
            if lang == "uk":
                stressifier = self._get_uk_stressifier()
                if stressifier:
                    try:
                        stressed = stressifier(phonetic_text)
                        stressed = re.sub(r"([аеєиіїоуюяАЕЄИІЇОУЮЯ])\u0301", r"+\1", stressed)
                        stressed = re.sub(r"([аеєиіїоуюяАЕЄИІЇОУЮЯ])´", r"+\1", stressed)
                        phonetic_text = stressed
                    except Exception as e:
                        print(f"[TTSSmart] Ошибка uk stress: {e}", file=sys.stderr)
            elif lang == "ru":
                accentizer = self._get_ru_accentizer()
                if accentizer:
                    try:
                        phonetic_text = accentizer.process_all(phonetic_text)
                    except Exception as e:
                        print(f"[TTSSmart] Ошибка ru accent: {e}", file=sys.stderr)
            elif lang == "mixed":
                # В смешанном тексте адаптируем украинские гласные под фонетику перед ruaccent
                accentizer = self._get_ru_accentizer()
                if accentizer:
                    try:
                        adapted = (phonetic_text
                                   .replace("і", "и").replace("І", "И")
                                   .replace("ї", "йи").replace("Ї", "Йи")
                                   .replace("є", "е").replace("Є", "Е")
                                   .replace("ґ", "г").replace("Ґ", "Г"))
                        phonetic_text = accentizer.process_all(adapted)
                    except Exception:
                        pass
        else:
            # Для edge_smart и clone_cloud: удаляем знак '+', чтобы синтезатор не читал "плюс"
            phonetic_text = phonetic_text.replace("+", "")

            # Фонетическая адаптация украинских букв для русскоязычного синтезатора
            if lang in ("ru", "mixed"):
                phonetic_text = (phonetic_text
                                .replace("і", "и").replace("І", "И")
                                .replace("ї", "йи").replace("Ї", "Йи")
                                .replace("є", "е").replace("Є", "Е")
                                .replace("ґ", "г").replace("Ґ", "Г"))

        return subtitle_text, phonetic_text

    # -------------------------------------------------------------------------
    # 4. Движки синтеза (Engines)
    # -------------------------------------------------------------------------
    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(coro)).result()
        else:
            return asyncio.run(coro)

    async def _synth_edge_single(self, text: str, voice: str, out_path: Path, rate: str = "+0%") -> bool:
        import edge_tts
        for attempt in range(1, 4):
            try:
                comm = edge_tts.Communicate(text, voice, rate=rate)
                await comm.save(str(out_path))
                if out_path.exists() and out_path.stat().st_size > 1000:
                    return True
            except Exception as e:
                if attempt == 3:
                    print(f"[TTSSmart] Edge-TTS голос {voice} не ответил: {e}", file=sys.stderr)
            await asyncio.sleep(0.5 + attempt * 0.5)
        return False

    def synthesize_edge_smart(self, text: str, lang: str, out_path: Path, speaker: str = "male", rate: str = "+0%") -> bool:
        """Синтез через Edge-TTS с интеллектуальным fallback."""
        voice_map = {
            "uk": {"male": "uk-UA-OstapNeural", "female": "uk-UA-PolinaNeural"},
            "ru": {"male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"}
        }

        spk_key = "female" if speaker.lower() in ("female", "polina", "svetlana") else "male"

        if lang == "mixed":
            # Разделяем на предложения и озвучиваем соответствующим голосом
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
            if not sentences:
                sentences = [text]

            temp_parts = []
            tmp_dir = Path(tempfile.mkdtemp(prefix="edge_mixed_"))
            try:
                for idx, sent in enumerate(sentences):
                    sent_lang = self.detect_language(sent, forced_lang="auto")
                    sent_lang = "uk" if sent_lang == "uk" else "ru"
                    voice = voice_map[sent_lang][spk_key]
                    part_file = tmp_dir / f"part_{idx:03d}.mp3"

                    _, p_text = self.preprocess_text(sent, sent_lang, engine="edge_smart")
                    ok = self._run_async(self._synth_edge_single(p_text, voice, part_file, rate=rate))
                    if not ok:
                        # Fallback на Silero для данного сегмента
                        ok = self.synthesize_silero(sent, sent_lang, part_file, speaker=speaker)
                    if not ok:
                        return False
                    temp_parts.append(part_file)

                # Склейка через FFmpeg concat
                list_file = tmp_dir / "list.txt"
                with open(list_file, "w", encoding="utf-8") as f:
                    for p in temp_parts:
                        f.write(f"file '{p.resolve()}'\n")

                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(list_file),
                    "-c:a", "libmp3lame" if out_path.suffix.lower() == ".mp3" else "pcm_s16le",
                    "-b:a", "192k", str(out_path)
                ]
                subprocess.run(cmd, check=True)
                return True
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            voice_lang = "uk" if lang == "uk" else "ru"
            voice = voice_map[voice_lang][spk_key]
            _, p_text = self.preprocess_text(text, lang, engine="edge_smart")
            ok = self._run_async(self._synth_edge_single(p_text, voice, out_path, rate=rate))

            # Умный fallback: если Microsoft Edge временно не ответил для DmitryNeural,
            # переключаемся на качественный локальный Silero (aidar) для сохранения мужского голоса
            if not ok:
                print(f"[TTSSmart] Edge-TTS ({voice}) временно недоступен, fallback на локальный Silero...", file=sys.stderr)
                return self.synthesize_silero(text, lang, out_path, speaker=speaker)
            return True

    def synthesize_silero(self, text: str, lang: str, out_path: Path, speaker: str = "default") -> bool:
        """Синтез через локальный Silero V4 на CPU с точным контролем ударений (+)."""
        import torch

        torch.set_num_threads(2)
        device = torch.device("cpu")

        model_lang = "ua" if lang == "uk" else "ru"
        model_speaker = "v4_ua" if model_lang == "ua" else "v4_ru"

        local_hub_dir = Path.home() / ".cache/torch/hub/snakers4_silero-models_master"
        if model_lang not in self._silero_models:
            if local_hub_dir.exists():
                model, _ = torch.hub.load(
                    repo_or_dir=str(local_hub_dir),
                    model="silero_tts",
                    language=model_lang,
                    speaker=model_speaker,
                    source="local"
                )
            else:
                model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-models",
                    model="silero_tts",
                    language=model_lang,
                    speaker=model_speaker,
                    trust_repo=True
                )
            model.to(device)
            self._silero_models[model_lang] = model

        model = self._silero_models[model_lang]

        # Выбор голоса
        if model_lang == "ua":
            voice = "mykyta"
        else:
            voice = "baya" if speaker in ("female", "svetlana") else "aidar"

        _, p_text = self.preprocess_text(text, lang, engine="silero")

        tmp_raw = out_path.with_suffix(".raw.wav")
        try:
            audio = model.apply_tts(text=p_text, speaker=voice, sample_rate=48000)
            import wave
            import numpy as np
            audio_np = (audio.numpy() * 32767).astype(np.int16)
            with wave.open(str(tmp_raw), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(audio_np.tobytes())
        except Exception as e:
            print(f"[TTSSmart] Ошибка Silero синтеза: {e}", file=sys.stderr)
            return False

        if tmp_raw.exists():
            if out_path.suffix.lower() == ".mp3":
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(tmp_raw),
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    str(out_path)
                ]
                subprocess.run(cmd, check=True)
                tmp_raw.unlink()
            else:
                shutil.move(tmp_raw, out_path)
            return True
        return False

    def synthesize_clone_cloud(self, text: str, lang: str, out_path: Path, ref_voice: Optional[Path] = None) -> bool:
        """Клонирование голоса через HuggingFace Space с автоматическим fallback."""
        ref_voice = ref_voice or DEFAULT_REF_VOICE
        if not ref_voice.exists():
            print(f"[TTSSmart] Файл референса {ref_voice} не найден, переключаемся на edge_smart", file=sys.stderr)
            return self.synthesize_edge_smart(text, lang, out_path)

        try:
            from gradio_client import Client, handle_file
            print(f"[TTSSmart] Подключение к HF Space для клонирования голоса...", file=sys.stderr)
            client = Client("coqui/xtts")
            target_lang = "uk" if lang == "uk" else "ru"
            _, p_text = self.preprocess_text(text, lang, engine="clone_cloud")

            result = client.predict(
                prompt=p_text,
                language=target_lang,
                audio_file_pth=handle_file(str(ref_voice)),
                api_name="/predict"
            )
            if result and os.path.exists(result):
                shutil.copy(result, out_path)
                return True
        except Exception as e:
            print(f"[TTSSmart] Клонирование голоса недоступно ({e}), fallback на edge_smart", file=sys.stderr)

        return self.synthesize_edge_smart(text, lang, out_path)

    # -------------------------------------------------------------------------
    # 5. Студийная постобработка через FFmpeg
    # -------------------------------------------------------------------------
    @staticmethod
    def apply_studio_mastering(raw_path: Path, out_path: Path) -> bool:
        """Прогоняет аудио через фильтры highpass + acompressor + loudnorm EBU R128 (-14 LUFS)."""
        filter_chain = (
            "highpass=f=80,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,"
            "loudnorm=I=-14:TP=-1.5:LRA=11"
        )
        cmd = [
            "nice", "-n", "19", "ionice", "-c", "3",
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(raw_path),
            "-af", filter_chain,
            "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",
            str(out_path)
        ]
        res = subprocess.run(cmd)
        return res.returncode == 0

    # -------------------------------------------------------------------------
    # Главная точка входа
    # -------------------------------------------------------------------------
    def generate(
        self,
        text: str,
        out_file: Path,
        lang: str = "auto",
        engine: str = "edge_smart",
        speaker: str = "male",
        rate: str = "+0%",
        mastering: bool = True
    ) -> Tuple[bool, str, str]:
        """Генерирует звук и возвращает (успех, subtitle_text, detected_lang)."""
        detected_lang = self.detect_language(text, forced_lang=lang)
        subtitle_text, _ = self.preprocess_text(text, detected_lang, engine=engine)

        tmp_raw = out_file.with_suffix(".tmp_raw" + out_file.suffix)
        success = False

        if engine == "edge_smart":
            success = self.synthesize_edge_smart(text, detected_lang, tmp_raw, speaker=speaker, rate=rate)
        elif engine == "silero":
            success = self.synthesize_silero(text, detected_lang, tmp_raw, speaker=speaker)
        elif engine == "clone_cloud":
            success = self.synthesize_clone_cloud(text, detected_lang, tmp_raw)
        else:
            raise ValueError(f"Неизвестный движок: {engine}")

        if not success or not tmp_raw.exists():
            return False, subtitle_text, detected_lang

        if mastering:
            ok = self.apply_studio_mastering(tmp_raw, out_file)
            if tmp_raw.exists():
                tmp_raw.unlink()
            return ok, subtitle_text, detected_lang
        else:
            shutil.move(tmp_raw, out_file)
            return True, subtitle_text, detected_lang


def main():
    parser = argparse.ArgumentParser(description="Двуязычный синтезатор речи TTSSmart")
    parser.add_argument("--text", type=str, help="Текст для синтеза")
    parser.add_argument("--text-file", type=Path, help="Файл с текстом")
    parser.add_argument("--output", type=Path, required=True, help="Путь к результирующему файлу")
    parser.add_argument("--lang", type=str, default="auto", choices=["auto", "uk", "ru", "mixed"], help="Язык")
    parser.add_argument("--engine", type=str, default="edge_smart", choices=["edge_smart", "silero", "clone_cloud"], help="Движок")
    parser.add_argument("--speaker", type=str, default="male", help="Голос / спикер (male, female, aidar, mykyta, etc.)")
    parser.add_argument("--rate", type=str, default="+0%", help="Скорость речи (например +10%)")
    parser.add_argument("--no-mastering", action="store_true", help="Отключить FFmpeg мастеринг")
    parser.add_argument("--sub-out", type=Path, help="Файл для сохранения очищенного текста субтитров")

    args = parser.parse_args()

    if args.text_file and args.text_file.exists():
        raw_text = args.text_file.read_text(encoding="utf-8").strip()
    elif args.text:
        raw_text = args.text.strip()
    else:
        print("Ошибка: укажите --text или --text-file", file=sys.stderr)
        sys.exit(1)

    tts = TTSSmart()
    success, sub_text, detected_lang = tts.generate(
        text=raw_text,
        out_file=args.output,
        lang=args.lang,
        engine=args.engine,
        speaker=args.speaker,
        rate=args.rate,
        mastering=not args.no_mastering
    )

    if success:
        print(f"[TTSSmart] Успешно создано: {args.output}")
        print(f"  Язык: {detected_lang}")
        print(f"  Субтитры: {sub_text}")
        if args.sub_out:
            args.sub_out.write_text(sub_text, encoding="utf-8")
        sys.exit(0)
    else:
        print(f"[TTSSmart] Ошибка при синтезе!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
