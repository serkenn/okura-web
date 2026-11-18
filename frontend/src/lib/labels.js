// 欄の名前・列挙の値の日本語の表示（中間表現の語彙は英語のキー。値そのものは変えない）
import { FIELD_VOCAB, ENUM_VOCAB } from './labels_vocab.js';

export const FIELD = {
  ...FIELD_VOCAB, // 記録の欄（tools/labels_vocab.json）。下の手書きの名前が優先
  // 役割
  recipient: '受け取った人', payer: '支払った人', patient: '受診した人', payee: '支払先の人', donor: '寄附した人',
  liable_person: '保険料を負担すべき人', member: '加入者', insured: '被保険者', sender: '送った人', employer: '雇い主',
  employee: '従業員', person: '人', other_person: '相手の人', parent: '親', child: '子', spouse_a: '配偶者（1）', spouse_b: '配偶者（2）',
  adoptive_parent: '養親', adoptee: '養子', caregiver: '受託者', placed_person: '委託された人', owner: '持ち主・事業主',
  seller: '売った人', holder: '持っている人', filer: '提出した人', taxpayer: '納税者', worker: '働く人', creditor: '債権者',
  business_owner: '事業主', relative: '親族', dependent: '被扶養者', subject_person: '対象の人', decedent: '亡くなった人', heir: '相続人',
  policyholder: '契約者', borrower: '借りた人', lessor: '貸した人', lessee: '借りた人', petitioner: '請求した人', supporter: '扶養する人',
  // when
  on: '日付', from_on: 'いつから', to_on: 'いつまで', tax_year: '年分', fiscal_year: '年度',
  // 金額
  gross: '総支給額', amount: '金額', withholding_tax: '源泉徴収税額', social_insurance_withheld: '社会保険料',
  basic_pay: '基本給', overtime_pay: '残業代', commuting_allowance: '通勤手当', commuting_pass_value: '現物の定期券の額', bonus: '賞与',
  payment_amount: '支払金額', social_insurance: '社会保険料等の金額', special_collection_tax: '特別徴収の税額', housing_loan_credit: '住宅借入金等特別控除の額',
  consumption_tax: '消費税の額', return_gift_value: '返礼品の価額', fee: '手数料', proceeds: '譲渡の対価', acquisition_cost: '取得費',
  selling_expenses: '譲渡の費用', standard_monthly_remuneration: '標準報酬月額', credit_amount: '控除の額', prepayment_total: '予定納税額',
  notice_amount: '通知の額', paid_in_year: 'その年に払った額', reimbursed: '補塡された額', total_income: '合計所得金額', revenue: '収入金額',
  monthly_wage: '月給', hourly_wage: '時給', daily_wage: '日給',
  // 属性
  counterparty: '支払元・支払先', due_on: '支給日', payment_type: '支給の種類', incurred_on: '受診日', provider: '病院・薬局',
  medical_kinds: '医療費の区分', product_name: '品名', expense_category: '経費の科目', business_id: '事業', premium_type: '保険料の種類',
  recipient_name: '寄附先', recipient_type: '寄附先の種類', recipient_local_government_kind: '自治体の種類', recipient_local_government_code: '自治体の団体コード',
  onestop_request_municipality_code: 'ワンストップ特例の申請先', receipt_issued: '受領証明書あり', method: '方法', purpose: '目的',
  slip_type: '源泉徴収票の種類', year_end_adjusted: '年末調整済み', municipality_code: '市区町村コード', household_id: '世帯',
  householder: '世帯主', relation_to_householder: '世帯主との続柄', scheme: '制度', insurer_id: '保険者番号', capacity: '資格',
  branch_id: '支部', school_type: '学校の種類', attendance: '通学の形', course: '課程', category: '種別', description: '説明',
  basis: '根拠', ended_by: '終わった理由', benefit_type: '給付の種類', flow: '種類', contract_id: '保険の契約', note: 'メモ',
  pay_type: '支払の種類', document_type: '書類の種類', section: '欄', listed: '記載した', decision: '処分', reason: '理由',
  same_household: '同一の世帯', criterion: '基準', ratio: '割合', amounts: '金額の内訳', income_type: '収入の種類',
  annual_amount: '年間の額', estimated_amount: '見積額', estimated_as_of: '見積りの日', apply: '適用する', declare: '申告する',
};

export const ENUM = {
  ...ENUM_VOCAB,
  medical_treatment: '診療・治療', health_checkup: '健康診断（治療につながった）', specific_health_guidance: '特定保健指導', medicine: '医薬品',
  hospitalization: '入院', care_service: '介護サービス', manual_therapy: 'あん摩・はり・柔道整復', nursing_care: '看護', midwifery: '助産',
  transport: '通院の交通費', medical_device: '医療用器具', diaper: 'おむつ（証明あり）', deposit: '預り金', certified_other: 'その他（証明あり）',
  national_health_insurance: '国民健康保険', national_pension: '国民年金', health_insurance: '健康保険', employees_pension: '厚生年金',
  long_term_care_insurance: '介護保険', late_stage_elderly_medical: '後期高齢者医療', employment_insurance: '雇用保険', national_pension_fund: '国民年金基金',
  kyokai_kenpo: '協会けんぽ', health_insurance_society: '健康保険組合', seamen_insurance: '船員保険', national_public_servants_mutual_aid: '国家公務員共済',
  local_public_servants_mutual_aid: '地方公務員共済', private_school_mutual_aid: '私学共済', insured: '被保険者本人', dependent: '被扶養者',
  first: '第1号', second: '第2号', third: '第3号',
  school_act_article1: '学校教育法第1条の学校（高校・大学など）', specialized_training_college: '専修学校', miscellaneous_school: '各種学校',
  accredited_vocational_training: '認定職業訓練', full_time: '全日制・昼間', part_time: '定時制', correspondence: '通信制', evening: '夜間',
  householder: '世帯主', spouse: '配偶者', child: '子', parent: '父母', sibling: '兄弟姉妹', grandchild: '孫', grandparent: '祖父母',
  other_relative: 'その他の親族', cohabitant: '同居人', unregistered_spouse: '未届の配偶者',
  birth_mother: '出生（母）', birth_in_marriage: '婚姻中の出生', acknowledgment: '認知',
  bank_transfer: '振込', card: 'カード', electronic_payment: '電子決済', cash: '現金', in_kind: '現物',
  living_expenses: '生活費', tuition: '学費', medical_expenses: '医療費',
  salary: '給与', retirement: '退職', public_pension: '公的年金', payment_record: '支払調書',
  prefecture: '都道府県', municipality: '市町村', insurer: '保険者',
  regular: '定期の給与', domestic: '国内', foreign: '国外',
  final_return: '確定申告書', employee_dependents_declaration: '扶養控除等申告書', dependent_relative: '扶養親族', specific_relative: '特定親族',
  disabled_person: '障害者', widow_or_single_parent: '寡婦・ひとり親', working_student: '勤労学生', other: 'その他',
  based: '自己の勤労に基づく', not_based: '基づかない', employment: '雇用', independent_contract: '請負',
  medical_expense_deduction: '医療費控除', self_medication: 'セルフメディケーション税制',
  income_deduction: '所得控除', tax_credit: '税額控除', temporary: '一時的', recurring: '恒常的',
  actual_living: '実際の生活', resident_record: '住民票',
  business: '事業', real_estate: '不動産', unemployment_benefit: '失業給付', sickness_or_maternity_allowance: '傷病・出産手当金',
  scholarship_loan: '貸与の奨学金', scholarship_grant: '給付の奨学金', unspecified: '分けない',
  true: 'はい', false: 'いいえ',
};

export function fieldLabel(name) { return FIELD[name] || name; }
export function enumLabel(v, extra) { if (extra && extra[v]) return extra[v]; return ENUM[v] || v; }

// 概念の短い名前（結果の表の行）
export function conceptLabel(id) {
  const i = id.indexOf('.');
  return i >= 0 ? id.slice(i + 1) : id;
}

export const MEANS = {
  判断: { label: '質問', chip: 'undet' },
  事実: { label: '入力が必要', chip: 'warn' },
  注入: { label: '市区町村・保険', chip: 'info' },
  一次情報: { label: '端数', chip: 'oos' },
  公表待ち: { label: '国の発表待ち', chip: 'oos' },
};

export const ORIGIN = { 'ai-ocr': 'AI読み取り', 'inapp-agent': 'AI', user: '一時保存' };
export function originLabel(o) {
  if (!o) return '';
  if (ORIGIN[o]) return ORIGIN[o];
  if (o.startsWith('mcp:')) return '外部AI';
  if (o.startsWith('api:')) return '外部AI';
  if (o.startsWith('user:')) return '一時保存';
  return o;
}

// 値を人が読む形に（JSON をそのまま見せない）
export function prettyValue(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'はい' : 'いいえ';
  if (typeof v === 'number') return v.toLocaleString('ja-JP');
  if (typeof v === 'string') return enumLabel(v);
  if (Array.isArray(v)) return v.map(prettyValue).join('、');
  if (typeof v === 'object') {
    if ('num' in v && 'den' in v) return `${v.num}/${v.den}`;
    if ('from_on' in v) return `${v.from_on}〜${v.to_on || ''}`;
    if ('tax_year' in v) return `${v.tax_year}年分`;
    if ('fiscal_year' in v) return `${v.fiscal_year}年度`;
    if ('on' in v && Object.keys(v).length === 1) return v.on;
    if ('amount' in v && 'type' in v) return `${Number(v.amount).toLocaleString('ja-JP')}円`;
    return Object.entries(v).map(([k, x]) => `${fieldLabel(k)}：${prettyValue(x)}`).join('　');
  }
  return String(v);
}
