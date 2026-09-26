import os
import pickle
import time

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer

from src.configs import RESPONSES_FILE_PATH
from src.utilz.logger import logger_

device = "cuda" if torch.cuda.is_available() else "cpu"
t = time.time()
modelID = "BAAI/bge-base-en-v1.5"
logger_.info(f"Loading model {modelID} on {device}")
tokenizer = AutoTokenizer.from_pretrained(modelID, use_fast=True)
model = AutoModel.from_pretrained(modelID).to(device)
logger_.info(f"Model loading time: {(time.time() - t):.3f} sec")


class SemanticSearch:
    def __init__(self, model, tokenizer, file_path=RESPONSES_FILE_PATH):
        self.tokenizer = tokenizer
        self.model = model.to(device)
        self.data_path = file_path
        self.embed_path = self.data_path.replace(".txt", "_embeddings.pkl")
        self.substrings, self.embeddings = self.load_data()

    def process_text(self, query, substrings=None, top_k=5, from_file=False):
        if substrings is None:
            substrings = []

        if from_file:
            substrings, all_embeddings_array = self.substrings, self.embeddings
        else:
            all_embeddings_array = self._get_substrings_embeddings(substrings)

        query_embedding = self._get_query_embedding(query)
        top_indices, top_scores = self._calculate_similarity(query_embedding, all_embeddings_array, top_k)
        # logger.info(f"Top indices: {top_indices}, Top scores: {top_scores}")
        new_data_list = self._get_top_similar_texts(substrings, top_indices)
        # self._log_processed_query(query)
        return {"content": new_data_list, "scores": top_scores}

    def _get_substrings_embeddings(self, substrings):
        all_embeddings = []
        for substr in substrings:
            embeddings = self._get_query_embedding(substr)
            all_embeddings.append(embeddings)
        all_embeddings_array = np.vstack(all_embeddings)
        return all_embeddings_array

    def _get_query_embedding(self, query):
        inputs = self.tokenizer(query, padding=True, truncation=True, return_tensors="pt", max_length=256, add_special_tokens=True, return_attention_mask=True, return_token_type_ids=False)
        with torch.no_grad():
            outputs = self.model(**inputs.to(device))

        attention_mask = inputs["attention_mask"]

        last_hidden = outputs.last_hidden_state.masked_fill(~attention_mask[..., None].bool(), 0.0)
        embeddings = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
        return embeddings.cpu().numpy()

    def _calculate_similarity(self, query_embedding, all_embeddings_array, top_k):
        all_embeddings_flat = all_embeddings_array.reshape(all_embeddings_array.shape[0], -1)
        scores = np.dot(all_embeddings_flat, query_embedding.T).squeeze()
        # logger.info(scores)
        scores_dict = dict(zip(np.arange(0, len(scores)), scores.tolist(), strict=False))
        # logger.info(f"score dict {pd.Series(scores_dict).sort_values(ascending=False)}")
        indices = pd.Series(scores_dict).sort_values(ascending=False).index.to_list()[:top_k]
        scores_list = pd.Series(scores_dict).sort_values(ascending=False).values.tolist()[:top_k]
        return indices, scores_list

    def _get_top_similar_texts(self, substrings, top_indices):
        return [substrings[i] for i in top_indices]

    def _log_processed_query(self, query):
        logger_.info(f"Processed query '{query}' with substrings and obtained similar texts.")

    def load_data(self):
        path = self.data_path
        embed_path = self.embed_path
        logger_.info(f"Loading responses from: {path}")
        with open(path) as file:
            data = file.read()
            substrings = [string for string in data.split("\n") if string]
            queries = [substring.split("|")[0] for substring in substrings]

        embeddings = []
        if os.path.exists(embed_path):
            logger_.info(f"Loading embedding from file: {embed_path}")
            with open(embed_path, "rb") as file:
                embeddings = pickle.load(file)
        else:
            logger_.info("Embeddings not found.")

        if len(queries) != len(embeddings):
            logger_.info("Generating new embeddings...")
            embeddings = self._get_substrings_embeddings(substrings=queries)
            with open(embed_path, "wb") as f:
                pickle.dump(embeddings, f)

        return substrings, embeddings


ss_obj = SemanticSearch(model, tokenizer)

# embeddings = ss_obj._get_substrings_embeddings()
# logger.info(len(embeddings))
