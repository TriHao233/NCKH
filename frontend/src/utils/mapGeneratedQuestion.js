import { bloomLevelLabel, questionTypeLabel } from '../constants/generationEnums';

function formatChoices(options, correctAnswer) {
  if (!options) {
    return [{ text: correctAnswer, isCorrect: true }];
  }

  if (Array.isArray(options)) {
    return options.map((option) => ({
      text: String(option),
      isCorrect: String(option) === String(correctAnswer),
    }));
  }

  if (typeof options === 'object') {
    return Object.entries(options).map(([key, value]) => {
      const text = `${key}. ${value}`;
      const isCorrect =
        String(correctAnswer) === String(key) ||
        String(correctAnswer) === String(value) ||
        String(correctAnswer) === text;
      return { text, isCorrect };
    });
  }

  return [{ text: String(options), isCorrect: true }];
}

export function mapGeneratedQuestions(questions = []) {
  return questions.map((question, index) => ({
    id: `Q-${index + 1}`,
    type: questionTypeLabel(question.question_type),
    bloom: bloomLevelLabel(question.bloom_level),
    text: question.question,
    choices: formatChoices(question.options, question.correct_answer),
    explanation: question.explanation,
  }));
}
