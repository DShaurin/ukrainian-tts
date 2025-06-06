from io import BytesIO
import requests
from os import getcwd
from os.path import exists, join, dirname
from espnet2.bin.tts_inference import Text2Speech
from enum import Enum
from .formatter import preprocess_text
from .stress import sentence_to_stress, stress_dict, stress_with_model
from torch import no_grad
import numpy as np
import time
import soundfile as sf
from kaldiio import load_ark


class Voices(Enum):
    """List of available voices for the model."""

    Tetiana = "tetiana"
    Mykyta = "mykyta"
    Lada = "lada"
    Dmytro = "dmytro"
    Oleksa = "oleksa"


class Stress(Enum):
    """Options how to stress sentence.
    - `dictionary` - performs lookup in dictionary, taking into account grammatical case of a word and its' neighbors
    - `model` - stress using transformer model"""

    Dictionary = "dictionary"
    Model = "model"


class TTS:
    """ """

    def __init__(self, cache_folder=None, device="cpu") -> None:
        """
        Class to setup a text-to-speech engine, from download to model creation.  \n
        Downloads or uses files from `cache_folder` directory.  \n
        By default stores in current directory."""
        self.device = device
        self.__setup_cache(cache_folder)

    def tts(self, text: str, voice: str, stress: str, output_fp=BytesIO(), format='WAV', subtype='PCM_16'):
        """
        Run a Text-to-Speech engine and output to `output_fp` BytesIO-like object.
        - `text` - your model input text.
        - `voice` - one of predefined voices from `Voices` enum.
        - `stress` - stress method options, predefined in `Stress` enum.
        - `output_fp` - file-like object output. Stores in RAM by default.
        - `format` - see soundfile.available_formats(). (default is 'WAV')
        - `subtype` - see soundfile.available_subtypes(). (default is 'PCM_16')
        """

        if stress not in [option.value for option in Stress]:
            raise ValueError(
                f"Invalid value for stress option selected! Please use one of the following values: {', '.join([option.value for option in Stress])}."
            )

        if stress == Stress.Model.value:
            stress = True
        else:
            stress = False
        if voice not in [option.value for option in Voices]:
            if voice not in self.xvectors.keys():
                raise ValueError(
                    f"Invalid value for voice selected! Please use one of the following values: {', '.join([option.value for option in Voices])}."
                )

        text = preprocess_text(text)
        text = sentence_to_stress(text, stress_with_model if stress else stress_dict)

        # synthesis
        with no_grad():
            start = time.time()
            synt = self.synthesizer(text, spembs=self.xvectors[voice][0])
            wav = synt["wav"]

        rtf = (time.time() - start) / (len(wav) / self.synthesizer.fs)
        print(f"RTF = {rtf:5f}")

        sf.write(
            output_fp,
            wav.view(-1).cpu().numpy(),
            self.synthesizer.fs,
            subtype,
            format=format,
        )

        output_fp.seek(0)

        return output_fp, text

    def __setup_cache(self, cache_folder=None):
        """Downloads models and stores them into `cache_folder`. By default stores in current directory."""
        release_number = "v6.0.0"
        print(
            f"downloading https://github.com/robinhad/ukrainian-tts/releases/download/{release_number}"
        )
        model_link = f"https://github.com/robinhad/ukrainian-tts/releases/download/{release_number}/model.pth"
        config_link = f"https://github.com/robinhad/ukrainian-tts/releases/download/{release_number}/config.yaml"
        speakers_link = f"https://github.com/robinhad/ukrainian-tts/releases/download/{release_number}/spk_xvector.ark"
        feat_stats_link = f"https://github.com/robinhad/ukrainian-tts/releases/download/{release_number}/feats_stats.npz"

        if cache_folder is None:
            cache_folder = "."

        model_path = join(cache_folder, "model.pth")
        config_path = join(cache_folder, "config.yaml")
        speakers_path = join(cache_folder, "spk_xvector.ark")
        feat_stats_path = join(getcwd(), "feats_stats.npz")

        self.__download(model_link, model_path)
        self.__download(config_link, config_path)
        self.__download(speakers_link, speakers_path)
        self.__download(feat_stats_link, feat_stats_path)
        print("downloaded.")

        self.synthesizer = Text2Speech(
            train_config=config_path, model_file=model_path, device=self.device
        )
        self.xvectors = {k: v for k, v in load_ark(speakers_path)}

    def __download(self, url, file_name):
        """Downloads file from `url` into local `file_name` file."""
        if not exists(file_name):
            if not exists(dirname(file_name)):
                raise ValueError(f'Directory "{dirname(file_name)}" doesn\'t exist!')
            print(f"Downloading {file_name}")
            r = requests.get(url, allow_redirects=True)
            with open(file_name, "wb") as file:
                file.write(r.content)
        else:
            print(f"Found {file_name}. Skipping download...")
