<?php

namespace local_nckh\external;

defined('MOODLE_INTERNAL') || die();

use external_api;
use external_function_parameters;
use external_single_structure;
use external_value;

final class find_question extends external_api {
    public static function execute_parameters(): external_function_parameters {
        return new external_function_parameters([
            'idempotencykey' => new external_value(PARAM_ALPHANUMEXT, 'Stable publication key'),
        ]);
    }

    public static function execute(string $idempotencykey): array {
        $params = self::validate_parameters(self::execute_parameters(), ['idempotencykey' => $idempotencykey]);
        $mapping = \local_nckh\question_service::mapping_by_idempotency($params['idempotencykey']);
        if (!$mapping) {
            return ['found' => false, 'questionid' => 0, 'versionid' => '', 'contenthash' => ''];
        }
        \local_nckh\question_service::require_mapping_access($mapping);
        return ['found' => true] + get_question::result($mapping);
    }

    public static function execute_returns(): external_single_structure {
        return new external_single_structure([
            'found' => new external_value(PARAM_BOOL, 'Whether a mapping exists'),
            'questionid' => new external_value(PARAM_INT, 'Moodle question ID'),
            'versionid' => new external_value(PARAM_ALPHANUMEXT, 'QBankCTU version ID'),
            'contenthash' => new external_value(PARAM_ALPHANUMEXT, 'QBankCTU content hash'),
        ]);
    }
}
