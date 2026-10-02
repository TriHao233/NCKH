import React from 'react';
import './StructuredQuestion.css';

export function isStructuredQuestionType(value) {
  return ['sap_xep', 'ghep_cot'].includes(String(value || '').toLowerCase());
}

export function structuredEntries(options) {
  if (Array.isArray(options)) {
    return options.map((entry) => ({ key: String(entry.label), value: String(entry.text ?? '') }));
  }
  if (!options || typeof options !== 'object') return [];
  return Object.entries(options).map(([key, value]) => ({ key, value: String(value ?? '') }));
}

export default function StructuredQuestion({ questionType, options, onOptionChange, disabled = false }) {
  const type = String(questionType || '').toLowerCase();
  if (!isStructuredQuestionType(type)) return null;
  const entries = structuredEntries(options);
  if (!entries.length) return null;

  const renderEntries = (items) => (
    <ul className="structured-question-list">
      {items.map(({ key, value }) => (
        <li key={key}>
          <b>{key}.</b>
          {onOptionChange ? (
            <input
              className="field-input"
              value={value}
              disabled={disabled}
              aria-label={`Mục ${key}`}
              onChange={(event) => onOptionChange(key, event.target.value)}
            />
          ) : <span>{value}</span>}
        </li>
      ))}
    </ul>
  );

  if (type === 'sap_xep') {
    return (
      <div className="structured-question">
        <div className="structured-question-title">Các bước cần sắp xếp</div>
        {renderEntries(entries)}
      </div>
    );
  }

  return (
    <div className="structured-question structured-question-columns">
      <div>
        <div className="structured-question-title">Cột số</div>
        {renderEntries(entries.filter(({ key }) => /^\d+$/.test(key)))}
      </div>
      <div>
        <div className="structured-question-title">Cột chữ</div>
        {renderEntries(entries.filter(({ key }) => /^[a-z]+$/i.test(key)))}
      </div>
    </div>
  );
}
