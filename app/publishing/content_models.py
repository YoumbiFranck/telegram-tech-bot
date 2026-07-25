from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class SimpleMessage(BaseModel):
    type: Literal["simple_message"]
    content: str


class Quiz(BaseModel):
    type: Literal["quiz"]
    question: str
    options: list[str]
    correct_answer: str
    explanation: str = ""

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
    question: str
    options: list[str]
    correct_answer: str
    explanation: str = ""

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
