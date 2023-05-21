from SPARQLWrapper import SPARQLWrapper, JSON
import pymorphy2
import logging
import dateparser
import spacy
import re


class Lemma:
    morph = pymorphy2.MorphAnalyzer()

    @staticmethod
    def lemmatize_word(word: str) -> str:
        parsed_word = Lemma.morph.parse(word)[0]
        return parsed_word.normal_form

    @staticmethod
    def lemmatize_sentence(sentence: str) -> str:
        return ' '.join([Lemma.lemmatize_word(word) for word in sentence.split()])


class Person:
    sparql_endpoint = "http://dbpedia.org/sparql"
    nlp = spacy.load("ru_core_news_sm")
    date_pattern = r"\b(?:\d{1,2}\s+\w+\s+\d{4}|(?:(?<!\d)\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?!\d)|\d{4}[./-]\d" \
                   r"{1,2}[./-]\d{1,2}))\b"

    def __init__(self, input_fact: str = '') -> None:
        self.__init_sparql()

        doc_fact = self.nlp(input_fact)
        self.name = []
        self.birth_date = {}
        self.birth_place = []
        self.persons = []

        for token in doc_fact:
            if token.ent_type_ == "PER":
                self.name.append(token.text)
            # elif token.ent_type_ == "DATE":
            #     self.birth_date.append(token.text)
            elif token.ent_type_ == "LOC":
                self.birth_place.append(Lemma.lemmatize_word(token.text))

        if not self.birth_date and (extracted_date := re.findall(self.date_pattern, input_fact)):
            extracted_date = extracted_date[0]
            date = dateparser.parse(extracted_date)
            self.birth_date = {
                'text_date': extracted_date,
                'datetime_date': date,
            }

    def __init_sparql(self) -> None:
        self.sparql = SPARQLWrapper(self.sparql_endpoint)
        self.sparql.setReturnFormat(JSON)

    def generate_run_sparql_query(self) -> None:
        for per in list(reversed(self.name)):
            query = f"""
                SELECT ?person ?name ?birthDate ?birthPlace ?nationality ?profession ?education
                WHERE {{
                    ?person rdf:type dbo:Person ;
                            foaf:name ?name ;
                            dbo:birthDate ?birthDate .
                    OPTIONAL {{
                        ?person dbo:birthPlace ?birthPlace_resource .
                        ?birthPlace_resource rdfs:label ?birthPlace .
                        FILTER (LANGMATCHES(LANG(?birthPlace), "ru"))
                    }}
                    FILTER (LANGMATCHES(LANG(?name), "ru"))
                    FILTER (REGEX(?name, "{per}", "i"))
                }}
            """

            self.sparql.setQuery(query)
            self.sparql.setReturnFormat(JSON)
            results = self.sparql.query().convert()
            if not results["results"]["bindings"]:
                continue

            for result in results["results"]["bindings"]:
                result_name = result.get("name", {}).get("value", "")
                result_birth_date = result.get("birthDate", {}).get("value", "")
                result_birth_place = result.get("birthPlace", {}).get("value", "")

                self.persons.append({
                    "name": result_name,
                    "birthDate": result_birth_date,
                    "birthPlace": Lemma.lemmatize_sentence(result_birth_place),
                })

    def compare_fact_with_knowledge(self) -> bool:
        self.generate_run_sparql_query()
        if not self.persons:
            logging.warning('Knowledge was not found in dbpedia')
            return False

        for found_person in self.persons:
            if all(per in found_person["name"] for per in self.name):
                if self.birth_date.get("datetime_date") \
                        and dateparser.parse(found_person["birthDate"]) != self.birth_date.get("datetime_date"):
                    continue
                if all(bp in found_person["birthPlace"] for bp in self.birth_place):
                    return True

        return False


if __name__ == "__main__":
    pers = Person("Владимир Ковалевский родился на Украине")
    pers.compare_fact_with_knowledge()
