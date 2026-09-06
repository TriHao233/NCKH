<?php

namespace local_nckh\external;

defined('MOODLE_INTERNAL') || die();

use external_api;
use external_function_parameters;
use external_single_structure;
use external_value;

final class get_question extends external_api {
    public static function execute_parameters(): external_function_parameters {
        return new external_function_parameters([
            'questionid' => new external_value(PARAM_INT, 'Moodle question ID'),
        ]);
    }

    public static function execute(int $questionid): array {
        $params = self::validate_parameters(self::execute_parameters(), ['questionid' => $questionid]);
        $mapping = \local_nckh\question_service::mapping_by_question($params['questionid']);
        if (!$mapping) {
            throw new \invalid_parameter_exception('Question is not managed by QBankCTU.');
        }
        \local_nckh\question_service::require_mapping_access($mapping);
        return self::result($mapping);
    }

    public static function result(\stdClass $mapping): array {
        return [
            'questionid' => (int)$mapping->questionid,
            'versionid' => $mapping->versionid,
            'contenthash' => $mapping->contenthash,
        ];
    }

    public static function execute_returns(): external_single_structure {
        return new external_single_structure([
            'questionid' => new external_value(PARAM_INT, 'Moodle question ID'),
            'versionid' => new external_value(PARAM_ALPHANUMEXT, 'QBankCTU version ID'),
            'contenthash' => new external_value(PARAM_ALPHANUMEXT, 'QBankCTU content hash'),
        ]);
    }
}
