from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class SimpleMessage(BaseModel):
    type: Literal["simple_message"]
    content: str


# Limites de l'API Telegram pour les polls (stables depuis des années) :
# question 1-300 caractères, 2-10 options de 1-100 caractères chacune,
# explication de quiz 0-200 caractères.
class Quiz(BaseModel):
    type: Literal["quiz"]
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)
    correct_answer: str
    explanation: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def check_options_length(self) -> "Quiz":
        for option in self.options:
            if not 1 <= len(option) <= 100:
                raise ValueError(f"option {option!r} must be 1-100 characters long")
        return self

    @model_validator(mode="after")
    def check_correct_answer_in_options(self) -> "Quiz":
        if self.correct_answer not in self.options:
            raise ValueError(
                f"correct_answer {self.correct_answer!r} is not one of options {self.options!r}"
            )
        return self


class Image(BaseModel):
    type: Literal["image"]
    content: str = ""
    url: str


class ImagePoll(BaseModel):
    type: Literal["image_poll"]
    image_url: str
    caption: str = ""
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)
    correct_answer: str
    explanation: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def check_options_length(self) -> "ImagePoll":
        for option in self.options:
            if not 1 <= len(option) <= 100:
                raise ValueError(f"option {option!r} must be 1-100 characters long")
        return self

    @model_validator(mode="after")
    def check_correct_answer_in_options(self) -> "ImagePoll":
        if self.correct_answer not in self.options:
            raise ValueError(
                f"correct_answer {self.correct_answer!r} is not one of options {self.options!r}"
            )
        return self


ContentItem = Annotated[
    Union[SimpleMessage, Quiz, Image, ImagePoll],
    Field(discriminator="type"),
]
