import { bloomLevelLabel, difficultyLabel, questionTypeLabel } from '../constants/generationEnums.js';

export function formatChoices(options, correctAnswer) {
  const correctValues = String(correctAnswer || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

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
        correctValues.includes(String(key)) ||
        correctValues.includes(String(value)) ||
        correctValues.includes(text) ||
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
    id: question.question_id || question.id || `Q-${index + 1}`,
    persistedId: question.question_id || question.id || null,
    questionCode: question.question_code || `Q-${index + 1}`,
    currentVersion: question.current_version || 1,
    currentVersionId: question.current_version_id || null,
    reviewStatus: question.review_status || 'DRAFT',
    questionType: question.question_type,
    bloomLevel: question.bloom_level,
    type: questionTypeLabel(question.question_type),
    bloom: bloomLevelLabel(question.bloom_level),
    difficulty: question.difficulty || null,
    difficultyLabel: difficultyLabel(question.difficulty),
    text: question.question,
    rawOptions: question.options,
    correctAnswer: question.correct_answer,
    choices: formatChoices(question.options, question.correct_answer),
    explanation: question.explanation,
    sourceContext: question.source_context,
    sourceKeywords: question.source_keywords || [],
    falseMutation: question.false_mutation || null,
  }));
}
