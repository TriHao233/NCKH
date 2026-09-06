<?php

namespace local_nckh;

defined('MOODLE_INTERNAL') || die();

final class question_service {
    public static function mapping_by_idempotency(string $idempotencykey): ?\stdClass {
        global $DB;
        return $DB->get_record('local_nckh_question_map', ['idempotencykey' => $idempotencykey]) ?: null;
    }

    public static function mapping_by_question(int $questionid): ?\stdClass {
        global $DB;
        return $DB->get_record('local_nckh_question_map', ['questionid' => $questionid]) ?: null;
    }

    public static function require_mapping_access(\stdClass $mapping): void {
        global $DB;
        $category = $DB->get_record('question_categories', ['id' => $mapping->categoryid], '*', MUST_EXIST);
        $context = \context::instance_by_id($category->contextid, MUST_EXIST);
        \external_api::validate_context($context);
        require_capability('local/nckh:publishquestion', $context);
    }

    public static function import(
        int $courseid,
        int $categoryid,
        string $idempotencykey,
        string $payloadjson
    ): \stdClass {
        global $CFG, $DB;
        require_once($CFG->dirroot . '/question/format/xml/format.php');

        $course = get_course($courseid);
        $category = $DB->get_record('question_categories', ['id' => $categoryid], '*', MUST_EXIST);
        $context = \context::instance_by_id($category->contextid, MUST_EXIST);
        \external_api::validate_context($context);
        require_capability('local/nckh:publishquestion', $context);
        if ((int)$context->get_course_context()->instanceid !== $courseid) {
            throw new \invalid_parameter_exception('Question category does not belong to the requested course.');
        }

        $payload = json_decode($payloadjson, true, 64, JSON_THROW_ON_ERROR);
        self::validate_payload($payload);
        $lockfactory = \core\lock\lock_config::get_lock_factory('local_nckh');
        $lock = $lockfactory->get_lock('publication:' . $idempotencykey, 30);
        if (!$lock) {
            throw new \moodle_exception('Could not acquire the publication lock.', 'local_nckh');
        }
        try {
            $existing = self::mapping_by_idempotency($idempotencykey);
            if ($existing) {
                self::require_mapping_access($existing);
                if ($existing->versionid !== $payload['version_id'] || $existing->contenthash !== $payload['content_hash']) {
                    throw new \invalid_parameter_exception('Idempotency key was already used for different content.');
                }
                return $existing;
            }

            $xml = self::to_xml($payload);
            $directory = make_temp_directory('local_nckh');
            $filename = tempnam($directory, 'question-');
            file_put_contents($filename, $xml, LOCK_EX);
            try {
                $format = new \qformat_xml();
                $format->setCategory($category);
                $format->setContexts([$context]);
                $format->setCourse($course);
                $format->setFilename($filename);
                $format->setRealfilename('qbankctu.xml');
                $format->setMatchgrades('nearest');
                $format->setStoponerror(true);
                $format->displayprogress = false;
                if (!$format->importpreprocess() || !$format->importprocess() || !$format->importpostprocess()) {
                    throw new \moodle_exception('Question import failed.', 'local_nckh');
                }
            } finally {
                @unlink($filename);
            }

            $sql = "SELECT q.id
                  FROM {question} q
                  JOIN {question_versions} qv ON qv.questionid = q.id
                  JOIN {question_bank_entries} qbe ON qbe.id = qv.questionbankentryid
                 WHERE qbe.questioncategoryid = :categoryid AND qbe.idnumber = :idnumber
              ORDER BY qv.version DESC";
            $questionid = $DB->get_field_sql($sql, [
                'categoryid' => $categoryid,
                'idnumber' => $payload['external_key'],
            ], MUST_EXIST);
            $now = time();
            $mapping = (object)[
                'idempotencykey' => $idempotencykey,
                'questionid' => $questionid,
                'versionid' => $payload['version_id'],
                'contenthash' => $payload['content_hash'],
                'payloadhash' => hash('sha256', $payloadjson),
                'courseid' => $courseid,
                'categoryid' => $categoryid,
                'timecreated' => $now,
                'timemodified' => $now,
            ];
            $mapping->id = $DB->insert_record('local_nckh_question_map', $mapping);
            return $mapping;
        } finally {
            $lock->release();
        }
    }

    private static function validate_payload(array $payload): void {
        $required = ['external_key', 'version_id', 'content_hash', 'name', 'questiontext', 'moodle_qtype'];
        foreach ($required as $field) {
            if (!isset($payload[$field]) || trim((string)$payload[$field]) === '') {
                throw new \invalid_parameter_exception('Missing payload field: ' . $field);
            }
        }
        $supported = ['multichoice', 'truefalse', 'shortanswer', 'matching', 'ordering'];
        if (!in_array($payload['moodle_qtype'], $supported, true)) {
            throw new \invalid_parameter_exception('Unsupported Moodle question type.');
        }
    }

    private static function xml(string $value): string {
        return htmlspecialchars($value, ENT_XML1 | ENT_QUOTES, 'UTF-8');
    }

    private static function answer(string $text, float $fraction, string $feedback = ''): string {
        return '<answer fraction="' . $fraction . '"><text>' . self::xml($text) . '</text>'
            . '<feedback><text>' . self::xml($feedback) . '</text></feedback></answer>';
    }

    private static function answer_keys(array $payload): array {
        return array_values(array_filter(array_map(
            fn($value) => strtoupper(trim($value)),
            preg_split('/[,;|]/', (string)($payload['correct_answer'] ?? ''))
        )));
    }

    private static function to_xml(array $payload): string {
        $qtype = $payload['moodle_qtype'];
        $options = $payload['options'] ?? [];
        $correct = self::answer_keys($payload);
        $feedback = (string)($payload['feedback'] ?? '');
        $common = '<name><text>' . self::xml($payload['name']) . '</text></name>'
            . '<questiontext format="html"><text>' . self::xml($payload['questiontext']) . '</text></questiontext>'
            . '<generalfeedback format="html"><text>' . self::xml($feedback) . '</text></generalfeedback>'
            . '<defaultgrade>1</defaultgrade><penalty>0.3333333</penalty><hidden>0</hidden>'
            . '<idnumber>' . self::xml($payload['external_key']) . '</idnumber>';
        $body = '';
        if ($qtype === 'truefalse') {
            $istrue = in_array($correct[0] ?? '', ['A', 'TRUE', 'T', 'ĐÚNG', 'DUNG'], true);
            $body = self::answer('true', $istrue ? 100 : 0, $feedback)
                . self::answer('false', $istrue ? 0 : 100, $feedback);
        } else if ($qtype === 'shortanswer') {
            $body = '<usecase>0</usecase>';
            foreach ($correct as $value) {
                $body .= self::answer($value, 100, $feedback);
            }
        } else if ($qtype === 'matching') {
            preg_match_all('/(\d+)\s*-\s*([A-Za-z])/', (string)$payload['correct_answer'], $matches, PREG_SET_ORDER);
            foreach ($matches as $match) {
                $body .= '<subquestion format="html"><text>' . self::xml((string)$options[$match[1]]) . '</text>'
                    . '<answer><text>' . self::xml((string)$options[strtoupper($match[2])]) . '</text></answer></subquestion>';
            }
        } else if ($qtype === 'ordering') {
            $rank = array_flip($correct);
            foreach ($options as $key => $value) {
                $body .= '<answer fraction="0"><text>' . self::xml((string)$value) . '</text><correctorder>'
                    . ((int)$rank[strtoupper((string)$key)] + 1) . '</correctorder></answer>';
            }
        } else {
            $multiple = ($payload['source_type'] ?? '') === 'nhieu_lua_chon';
            $fraction = $multiple && count($correct) ? 100 / count($correct) : 100;
            $body = '<single>' . ($multiple ? 'false' : 'true') . '</single><shuffleanswers>true</shuffleanswers>';
            foreach ($options as $key => $value) {
                $body .= self::answer((string)$value, in_array(strtoupper((string)$key), $correct, true) ? $fraction : 0, $feedback);
            }
        }
        return '<?xml version="1.0" encoding="UTF-8"?><quiz><question type="' . self::xml($qtype) . '">'
            . $common . $body . '</question></quiz>';
    }
}
