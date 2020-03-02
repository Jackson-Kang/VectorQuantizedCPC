import argparse
import json
import csv
from pathlib import Path
import torch
import numpy as np
import librosa
from model import Vocoder, Encoder
from tqdm import tqdm


def convert(args, params):
    data_dir = Path(args.data_dir)

    with open(data_dir / "speakers.csv") as file:
        reader = csv.reader(file)
        speakers = sorted([speaker for speaker, in reader])

    with open(args.synthesis_list) as file:
        reader = csv.reader(file)
        synthesis_list = [(data_dir.parent / mel_path, speaker) for mel_path, speaker in reader]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = Encoder(in_channels=params["preprocessing"]["num_mels"],
                    encoder_channels=params["model"]["encoder_channels"],
                    z_dim=params["model"]["z_dim"],
                    c_dim=params["model"]["c_dim"])
    model.to(device)

    print("Load checkpoint from: {}:".format(args.cpc_checkpoint))
    checkpoint = torch.load(args.cpc_checkpoint, map_location=lambda storage, loc: storage)
    model.load_state_dict(checkpoint["model"])
    model.eval()

    vocoder = Vocoder(in_channels=params["model"]["z_dim"],
                  num_speakers=params["model"]["vocoder"]["num_speakers"],
                  speaker_embedding_dim=params["model"]["vocoder"]["speaker_embedding_dim"],
                  conditioning_channels=params["model"]["vocoder"]["conditioning_channels"],
                  embedding_dim=params["model"]["vocoder"]["embedding_dim"],
                  rnn_channels=params["model"]["vocoder"]["rnn_channels"],
                  fc_channels=params["model"]["vocoder"]["fc_channels"],
                  bits=params["preprocessing"]["bits"],
                  hop_length=params["preprocessing"]["hop_length"])
    vocoder.to(device)

    print("Load checkpoint from: {}:".format(args.checkpoint))
    checkpoint = torch.load(args.checkpoint, map_location=lambda storage, loc: storage)
    vocoder.load_state_dict(checkpoint["model"])

    gen_dir = Path(args.out_dir)
    gen_dir.mkdir(exist_ok=True, parents=True)

    for mel_path, speaker_id in tqdm(synthesis_list):
        mel = np.load(mel_path.with_suffix(".mel.npy"))
        mel = torch.FloatTensor(mel).unsqueeze(0).to(device)
        speaker = torch.LongTensor([speakers.index(speaker_id)]).to(device)

        with torch.no_grad():
          z, c, _, _ = model(mel)
          output = vocoder.generate(c, speaker)

        utterance_id = mel_path.stem.split("_")[1]
        path = Path(gen_dir) / "{}_{}.wav".format(speaker_id, utterance_id)
        librosa.output.write_wav(path, output.astype(np.float32), sr=params["preprocessing"]["sample_rate"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, help="Checkpoint path to resume")
    parser.add_argument("--cpc-checkpoint", type=str, default=None, help="Checkpoint path to restore CPC model")
    parser.add_argument("--data-dir", type=str)
    parser.add_argument("--out-dir", type=str)
    parser.add_argument("--synthesis-list", type=str)
    args = parser.parse_args()
    with open("config.json") as file:
        params = json.load(file)
    convert(args, params)
