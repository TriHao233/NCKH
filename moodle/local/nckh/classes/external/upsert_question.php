<?php

namespace local_nckh\external;

defined('MOODLE_INTERNAL') || die();

use external_api;
use external_function_parameters;
use external_single_structure;
use external_value;

final class upsert_question extends external_api {
    public static function execute_parameters(): external_function_parameters {
        return new external_function_parameters([
            'courseid' => new external_value(PARAM_INT, 'Course ID'),
            'categoryid' => new external_value(PARAM_INT, 'Question category ID'),
            'idempotencykey' => new external_value(PARAM_ALPHANUMEXT, 'Stable publication key'),
            'payloadjson' => new external_value(PARAM_RAW, 'Versioned QBankCTU payload'),
        ]);
    }

    public static function execute(int $courseid, int $categoryid, string $idempotencykey, string $payloadjson): array {
        $params = self::validate_parameters(self::execute_parameters(), compact(
            'courseid', 'categoryid', 'idempotencykey', 'payloadjson'
        ));
        $mapping = \local_nckh\question_service::import(
            $params['courseid'], $params['categoryid'], $params['idempotencykey'], $params['payloadjson']
        );
        return ['questionid' => (int)$mapping->questionid];
    }

    public static function execute_returns(): external_single_structure {
        return new external_single_structure([
            'questionid' => new external_value(PARAM_INT, 'Moodle question ID'),
        ]);
    }
}
