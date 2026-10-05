# Overview

### General information
:::warning[Please review the text below — it contains useful information]
:::

---
### Recommendations for Using HTTP Protocols
&emsp;To ensure optimal performance and reliability when interacting with our services, we recommend using the **HTTP/3** protocol (based on QUIC).

:::info[Benefits of HTTP/3:]
 - Faster connection establishment due to the use of UDP instead of TCP
 - Improved performance in unstable networks (e.g., mobile connections)
 - Reduced latency through built-in multiplexing without head-of-line blocking
 - Enhanced security with always-encrypted connections (similar to HTTPS)
:::

:::info[Compatibility]
&emsp;HTTP/3 is supported by most modern browsers and servers. While HTTP/1.1 and HTTP/2 remain supported for backward compatibility, HTTP/3 is the preferred protocol
:::

:::tip[Recommendation]
&emsp;When configuring client solutions and integrations, ensure that your technology stack supports HTTP/3 (e.g., curl with QUIC support, modern versions of Chrome, Firefox, nginx, etc.)
:::

---
### System Monitoring
:::info[]
&emsp;For real-time updates on our system performance and availability, please refer to our monitoring page: https://status.freedompay.kz/
:::

---
### Healthcheck
:::info[]
- To monitor the availability of our API services, you can send HTTP/2 requests to the following healthcheck endpoint:
https://api.freedompay.kz/status/healthcheck
- The endpoint returns a JSON response with the current status of the service. Example format:
`
{"status": "ok","time": "1970-01-01T00:00:00+00:00"}
`
- Explanation of response parameters:

| property | type | description  |
| --- | --- | --- |
| `status` |  string | Indicates the health or operational state of the service.
| `time` | string, ISO 8601 format | The UTC timestamp representing the moment the health check response was generated |
:::


# Overview

### General information
:::tip[]
- The Gateway API facilitates are the direct connection between merchants and FreedomPay, eliminating the need for payment pages, although those remain available if required
- You should read the Introduction section before starting
- If you have any questions, please contact your manager
:::

:::warning[]
**Attention!**
Connection requires a PCI DSS certificate!
:::

---
### About service
&emsp;FreedomPay is a universal payment acceptance tool for businesses.
&emsp;The service enables payment processing, payouts to bank cards, and card saving. These functionalities are divided into three main categories:

:::info[]
- **Payment Acceptance:** This section outlines the process by which {{project}} collects payments on behalf of the merchant and subsequently transfers the funds to the designated bank account. 
- **Payouts:** This section explains the procedure when {{project}} disburses funds to the user's bank card. 
- **Saving Cards:** This section covers the basic mechanics of saving cards. Once saved, these cards can be used for both receiving payments and making payments. 
:::

&emsp;Each documentation script includes all the queries that can be executed to implement the chosen script.

---
### Test cards
<Icon icon="material-outline-check_circle_outline"/> - **available**, <Icon icon="material-outline-highlight_off"/> - **not available**, <Icon icon="material-outline-lock_open"/> - **impossible**

#### Payment cards
| Card number        | 3DS            | auth    | clearing    | reverse     | refund      | card add    |
|--------------------|----------------|---------|-------------|-------------|-------------|-------------|
| 4716047261941981   | <Icon icon="material-outline-highlight_off"/>    | <Icon icon="material-outline-check_circle_outline"/> | <Icon icon="material-outline-check_circle_outline"/>     | <Icon icon="material-outline-highlight_off"/>       | <Icon icon="material-outline-check_circle_outline"/>     | <Icon icon="material-outline-check_circle_outline"/>     |
| 4916307416334310   | <Icon icon="material-outline-check_circle_outline"/>        | <Icon icon="material-outline-check_circle_outline"/> | <Icon icon="material-outline-check_circle_outline"/>     | <Icon icon="material-outline-highlight_off"/>       | <Icon icon="material-outline-highlight_off"/>       | <Icon icon="material-outline-check_circle_outline"/>     |
| 5367654276102126   | <Icon icon="material-outline-check_circle_outline"/>        | <Icon icon="material-outline-check_circle_outline"/> | <Icon icon="material-outline-highlight_off"/>       | <Icon icon="material-outline-check_circle_outline"/>     | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-check_circle_outline"/>     |
| 4939770956154989   | <Icon icon="material-outline-highlight_off"/>    | <Icon icon="material-outline-check_circle_outline"/> | <Icon icon="material-outline-highlight_off"/>       | <Icon icon="material-outline-check_circle_outline"/>     | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-check_circle_outline"/>     |
| 5335215945367703   | <Icon icon="material-outline-lock_open"/>     | <Icon icon="material-outline-highlight_off"/>   | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  |
| 4916109830832246   | <Icon icon="material-outline-lock_open"/>     | <Icon icon="material-outline-highlight_off"/>   | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  |
| 5548398681700148   | <Icon icon="material-outline-lock_open"/>     | <Icon icon="material-outline-highlight_off"/>   | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  |
| 5475102935853613   | <Icon icon="material-outline-lock_open"/> | <Icon icon="material-outline-highlight_off"/>   | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon icon="material-outline-lock_open"/>  | <Icon title="TEST" icon="material-outline-lock_open"/>  |
| 6224466455690681278   |<Icon icon="material-outline-highlight_off"/>  | <Icon icon="material-outline-check_circle_outline"/>    | <Icon icon="material-outline-check_circle_outline"/>  | <Icon icon="material-outline-check_circle_outline"/>   | <Icon icon="material-outline-check_circle_outline"/>  | <Icon icon="material-outline-check_circle_outline"/>  |
| 623275279933273424   |<Icon icon="material-outline-highlight_off"/>  | <Icon icon="material-outline-check_circle_outline"/>    | <Icon icon="material-outline-check_circle_outline"/>  | <Icon icon="material-outline-check_circle_outline"/>   | <Icon icon="material-outline-check_circle_outline"/>  | <Icon icon="material-outline-check_circle_outline"/>  |
| 62528733472390953   |<Icon icon="material-outline-highlight_off"/>  | <Icon icon="material-outline-check_circle_outline"/>    | <Icon icon="material-outline-check_circle_outline"/>  | <Icon icon="material-outline-check_circle_outline"/>   | <Icon icon="material-outline-check_circle_outline"/>  | <Icon icon="material-outline-check_circle_outline"/>  |

#### Payout cards

| Card number        | status         | description    |
|--------------------|----------------|------------|
| 4671593866478252   | <Icon icon="material-outline-check_circle_outline"/>    | success operation |
| 5325349472901311   | <Icon icon="material-outline-highlight_off"/>        | error code: 10000  |
| 4556046085041740   | <Icon icon="material-outline-highlight_off"/>        | error code: 10001 |
| 5543974702876045   | <Icon icon="material-outline-highlight_off"/>    | error code: 8888 |
| 5507841999732294   | <Icon icon="material-outline-highlight_off"/>     |  process turn to "success operation"  |
| 4532676596620704   | <Icon icon="material-outline-highlight_off"/>     | process turn to "error code: 10001"  |
| 6204500338419360939 |  <Icon icon="material-outline-check_circle_outline"/>   | success operation |
| 629656013969216940 |  <Icon icon="material-outline-check_circle_outline"/>   |  success operation  |
| 62861819783765929   |  <Icon icon="material-outline-check_circle_outline"/>  |  success operation  |

---
### Error codes
:::tip[]
**[Click here](https://customer.freedompay.kz/dev/error?lang=en)**
:::

---
### Support
:::info[If you found an inaccuracy or need help, feel free to reach out! 👋]
- **Email**: support@freedompay.kz
:::

# Overview

### Query Mechanics
&emsp;The API supports GET requests and POST requests with `Content-type` equal to `form-data` or `x-www-form-urlencoded`
It is recommended to maintain a delay of `1500–2000 milliseconds (1.5–2 seconds) `between consecutive payment API requests to prevent duplicate transactions and avoid triggering rate limiting or anti-fraud mechanisms  
&emsp;Data can be sent:
:::note[]
- GET method - data is passed in GET parameters; when transferring complex structured data, such as multidimensional arrays, the following notation format is used:
`{{domain}}/script.php?param_1=val&param_2[subParam_1]=val2& param_2[subParam_2]=val3&param_3=val4`
- POST method - data is transmitted in POST parameters. Structural data when working via POST are formed in a similar way.
- Via XML - requests are also transmitted by the Post method, only in the only pg_xml parameter, presented in XML form:<br>
```
<?xml version="1.0" encoding="utf-8"?><request><pg_param1>value1</pg_param><pg_param2>value2</pg_param></request>
```
:::

---
### Signature Formation
&emsp;Any messages (requests and responses) between FreedomPay and the merchant are signed. To create a signature, you need to concatenate the following with a separator `;`:

:::info[]
1. The name of the script being called (from the last `/` to the end or `?`).
2. All message fields in alphabetical order, including the random string `pg_salt`, which consists of an arbitrary number of digits and Latin letters.
3. Additionally:
- This rule is applied recursively to nested tags (only for XML).
- Fields with the same name are taken in the order they appear in the message.
4. The payment password `secret_key`, which is set in the store settings and is known only to the merchant and FreedomPay.
:::

&emsp;The resulting concatenated string must then be hashed using MD5, and the hash should be added to the request or response as an additional parameter `pg_sig`. The MD5 hash is recorded as a 32-character lowercase hexadecimal string.
Either party may add additional parameters to the request or response that are not specified in the documentation. These parameters also participate in the signature calculation. A message is not signed, and thus the fields `pg_salt` and `pg_sig` are absent only in one case – when FreedomPay could not identify the merchant and therefore does not know its `secret_key`. In such a case, the field `pg_error_code` (numeric error code) takes the value 9998. 
&emsp;For a complete list of possible values of the field `pg_error_code`, see the Error Code Reference section.

#### Example of request with signature
```bash
curl --location --request POST 'https://api.freedompay.kz/init_payment.php' \
--form 'pg_order_id=23' \
--form 'pg_merchant_id={{merchant_id}}' \
--form 'pg_amount=25' \
--form 'pg_description=Order description' \
--form 'pg_salt=some_random_string' \
--form 'pg_sig={{signature}}'
# Signature Formation:
'init_payment.php;25;Order description;{{merchant_id}};23;some_random_string;{{secret_key}}'
```

#### PHP example
```php
$merchantId = {{merchant_id}};
$secretKey = {{merchant_secret}};

$request = [
    'pg_order_id' => 23,
    'pg_merchant_id'=> $merchantId,
    'pg_amount' => 25,
    'pg_description' => 'Order description',
    'pg_salt' => 'some_random_string',
];

//generate a signature and add it to the array
ksort($request); //sort alphabetically
array_unshift($request, 'init_payment.php');
array_push($request, $secretKey);

$request['pg_sig'] = md5(implode(';', $request));

unset($request[0], $request[1]);
```

# Overview

### Payment
:::note[]
- This section outlines the methods available for card payments. Depending on the selected transaction type (one-step or two-step payment), the set of available methods varies
- A *one-step payment* is executed with a single request that simultaneously initiates authorization and funds withdrawal
- To send a request for processing a one-step payment in the Freedom Pay Gateway, you must specify `pg_auto_clearing = 1` in the request parameters
- A *two-step payment* is performed in two stages: first, authorization is carried out, during which the amount is blocked on the payer's account, and then a second request is sent for clearing (operation confirmation), which results in the actual withdrawal of funds
- To send a request for processing a two-step payment in the Freedom Pay Gateway, you must specify `pg_auto_clearing = 0` in the request parameters
:::

---
### Available statuses
:::warning[]
Watch out! The diagram will be coming soon!
:::

# Create payment

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/payment_page/:
    post:
      summary: Create payment
      deprecated: false
      description: >-
        :::warning[]

        There are two options for using the method:

        - direct data transfer from the merchant to FreedomPay

        - data transfer via the user's browser to FreedomPay

        :::


        :::info[]

        - When directly transferring data from the merchant to FreedomPay, the
        merchant must send data to init_payment.php.

        &emsp;When transferring data via the user's browser to FreedomPay, the
        merchant must redirect the user with the data to payment.php.

        - You can transfer arbitrary additional parameters whose names do not
        begin with pg_. All these parameters will be transferred to pg_check_url
        and pg_result_url.

        The names of additional merchant parameters must be unique.

        - After receiving the pg_redirect_url parameter, the user is redirected
        to the payment page, where the payer completes the payment.

        - If successful, the user will be redirected to the payment page.

        - If the merchant has not transferred all the parameters necessary to
        create a payment transaction (payment system, user's phone number and
        parameters necessary for the selected payment system), they are
        requested from the user on the freedompay.kz website.

        - Frame is an embeddable HTML element that loads page content from the
        Freedom Pay Gateway. It is used to display the payment form (e.g.,
        fields for entering the card number and CVV code) directly on the
        merchant's page.

        To invoke the Frame method, the parameter `pg_payment_route = frame`
        must be included in the request to the Freedom Pay Gateway.

        To use this method, you should contact your manager.

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error/pending*

        :::


        ![Merchant_API_V3-Payment
        page.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348669/image-preview)
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_order_id:
                  type: number
                  description: >-
                    * Payment ID in the merchant system. It is recommended to
                    keep this field unique
                  example: ''
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_currency:
                  description: '* Currency in which the amount is specified'
                  example: ''
                  type: string
                pg_description:
                  type: number
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                pg_testing_mode:
                  description: '* Creating a payment in test mode'
                  example: 0
                  type: integer
                pg_lifetime:
                  type: integer
                  minimum: 300
                  maximum: 604800
                  default: 86400
                  description: >-
                    * Time (in seconds) during which the payment must be
                    completed
                  example: 0
                pg_language:
                  type: string
                  format: ISO 639-1:2002
                  default: ru
                  examples:
                    - ru
                    - en
                    - kz
                    - kg
                    - uz
                  description: >-
                    * The language of the payment page can be synchronized with
                    the language of your application or website user
                  example: ''
                pg_user_id:
                  description: '* User ID in the merchant system'
                  example: ''
                  type: string
                pg_user_ip:
                  description: '* Client''s IP address'
                  example: ''
                  type: string
                pg_user_phone:
                  description: '* The user''s phone number (starting with the country code)'
                  example: ''
                  type: string
                pg_user_contact_email:
                  description: '* User''s contact email address'
                  example: ''
                  type: string
                pg_payment_method:
                  description: '* Payment method'
                  example: ''
                  type: string
                pg_request_method:
                  type: integer
                  description: '* GET'
                  example: ''
                pg_check_url:
                  type: integer
                  description: >-
                    URL to check the possibility of payment. Called before the
                    payment if supported by the payment system. If not specified
                  example: ''
                pg_result_url:
                  type: integer
                  description: >-
                    URL to report the result of the payment. Called after
                    payment on success or failure. If not specified
                  example: ''
                pg_success_url:
                  type: boolean
                  description: >-
                    * URL to which the user is sent in case of a successful
                    payment
                  example: ''
                pg_failure_url:
                  type: integer
                  description: >-
                    * URL to which the user is sent in case of unsuccessful
                    payment
                  example: ''
                pg_site_url:
                  description: >-
                    * URL of the store's site to show the customer a link to
                    return to the store after creating an invoice. Applies to
                    offline payment systems (cash).
                  example: ''
                  type: string
                pg_success_url_method:
                  type: boolean
                  description: >-
                    * Method for the button submitted to confirm payment.
                    Options: GET or POST. If selected
                  example: ''
                pg_failure_url_method:
                  description: >-
                    Method for the button submitted in case of payment failure.
                    Options: GET or POST. If selected
                  example: ''
                  type: string
                pg_param1:
                  description: '* Additional parameter 1'
                  example: ''
                  type: string
                pg_param2:
                  description: '* Additional parameter 2'
                  example: ''
                  type: string
                pg_param3:
                  description: '* Additional parameter 3'
                  example: ''
                  type: string
                pg_generate_qr:
                  description: >-
                    * Generate QR code with a link to the {{project}} payment
                    form in base64 format
                  example: ''
                  type: boolean
                pg_idempotency_key:
                  description: >-
                    * Idempotency key. Used to prevent duplicate request
                    creation. A unique value within the merchant's scope; the
                    same key cannot be used for different operations
                  example: ''
                  type: string
                pg_loyalty_id:
                  description: '* Identifier in the loyalty system'
                  example: ''
                  type: string
                pg_loyalty_amount:
                  description: '* Amount of accrued units in the loyalty system'
                  example: 0
                  type: number
                pg_freedom_id:
                  description: '* User identifier in the Freedom ecosystem'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
                pg_receipt_positions[0][count]:
                  type: integer
                  minimum: 1
                  description: '* Product quantity'
                  example: 0
                pg_receipt_positions[0][name]:
                  type: string
                  format: char
                  minLength: 1
                  description: '* Product name'
                  example: ''
                pg_receipt_positions[0][price]:
                  type: number
                  minimum: 0.01
                  maximum: 99999999
                  description: '* Price per unit'
                  example: 0
                pg_receipt_positions[0][tax_type]:
                  type: integer
                  enum:
                    - 0
                    - 3
                    - 7
                    - 11
                  x-apidog-enum:
                    - value: 0
                      name: ''
                      description: Without tax
                    - value: 3
                      name: ''
                      description: VAT 16/116
                    - value: 7
                      name: ''
                      description: VAT 10/110
                    - value: 11
                      name: ''
                      description: VAT 5/105
                  description: '* Tax type'
                  example: 0
                pg_receipt_positions[0][UnitCode]:
                  type: integer
                  description: '* Unit of measurement'
                  example: 0
                pg_receipt_positions[0][GTIN]:
                  description: '* Barcode'
                  example: ''
                  type: string
                pg_receipt_positions[0][NTIN]:
                  description: >-
                    * Barcode assigned to goods by the National Goods Catalog of
                    the Republic of Kazakhstan
                  example: ''
                  type: string
                pg_receipt_positions[0][mark_list][]:
                  type: array
                  items:
                    type: string
                  description: >-
                    Array of marking codes for labeled goods. Number of elements
                    must match the `count` value. 

                    Example: `"mark_list": ["code1"]` for count = 1,
                    `"mark_list": ["code1", "code2"]` for count = 2
                  example: ''
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: Payment ID
                  pg_status:
                    type: string
                    description: ok
                  pg_redirect_url:
                    type: string
                  pg_redirect_url_type:
                    type: string
                  pg_redirect_qr:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_redirect_url
                  - pg_redirect_url_type
                  - pg_redirect_qr
                  - pg_salt
                  - pg_sig
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_redirect_url
                  - pg_salt
                  - pg_redirect_url_type
                  - pg_sig
              examples:
                '1':
                  summary: Success
                  value: |
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>ok</pg_status>
                        <pg_payment_id>123456</pg_payment_id>
                        <pg_redirect_url>https://customer.freedompay.kz/</pg_redirect_url>
                        <pg_redirect_url_type>need data</pg_redirect_url_type>
                        <pg_redirect_qr>data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA...</pg_redirect_qr>
                        <pg_salt>some random string</pg_salt>
                        <pg_sig>signature-abc123</pg_sig>
                    </response>
                '2':
                  summary: Invalid Signature
                  value: |-
                    <?xml version="1.0" encoding="UTF-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>1100</pg_error_code>
                        <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Shows the result of the query
                  pg_error_code:
                    type: string
                    description: Error code ID
                  pg_error_description:
                    type: string
                    description: Text description of the error
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9890787-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Any amount

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/any_amount:
    post:
      summary: Any amount
      deprecated: false
      description: >-
        :::info[]

        - If you want the payer to enter the payment amount himself, you must
        use this method

        - When making a payment, the payer first gets to the form where he
        enters the amount of the payment

        - Then it is redirected to the payment page where the payment takes
        place

        :::


        #### Interaction diagram

        :::tip[]

        Status *success/error/pending*

        :::


        ![Merchant_API_V3-Any amount
        method.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348671/image-preview)
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_order_id:
                  type: number
                  description: >-
                    * Payment ID in the merchant system. It is recommended to
                    keep this field unique
                  example: ''
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_amount_interval_from:
                  description: '* The lower limit of the payment amount'
                  example: 0
                  type: integer
                pg_amount_interval_to:
                  description: '* The highest threshold for the payment amount'
                  example: 0
                  type: integer
                pg_currency:
                  description: '* Currency in which the amount is specified'
                  example: ''
                  type: string
                pg_description:
                  type: number
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                pg_testing_mode:
                  description: '* Creating a payment in test mode'
                  example: 0
                  type: integer
                pg_lifetime:
                  description: >-
                    * Time during which the payment must be completed (in
                    seconds)
                  example: 0
                  type: integer
                pg_language:
                  type: string
                  format: ISO 639-1:2002
                  default: ru
                  examples:
                    - ru
                    - en
                    - kz
                    - kg
                    - uz
                  description: >-
                    * The language of the payment page can be synchronized with
                    the language of your application or website user
                  example: ''
                pg_user_id:
                  description: '* User ID in the merchant system'
                  example: ''
                  type: string
                pg_user_ip:
                  description: '* Client''s IP address'
                  example: ''
                  type: string
                pg_user_phone:
                  description: '* The user''s phone number (starting with the country code)'
                  example: ''
                  type: string
                pg_user_contact_email:
                  description: '* User''s contact email address'
                  example: ''
                  type: string
                pg_payment_method:
                  description: '* Payment method'
                  example: ''
                  type: string
                pg_check_url:
                  type: integer
                  description: '* URL to check the possibility of payment'
                  example: ''
                pg_result_url:
                  type: integer
                  description: '* URL to report the result of the payment'
                  example: ''
                pg_success_url:
                  type: boolean
                  description: >-
                    * URL to which the user is sent in case of a successful
                    payment
                  example: ''
                pg_failure_url:
                  type: integer
                  description: >-
                    * URL to which the user is sent in case of unsuccessful
                    payment
                  example: ''
                pg_site_url:
                  description: '* Merchant''s site URL for returning the buyer after payment'
                  example: ''
                  type: string
                pg_success_url_method:
                  type: boolean
                  description: '* Method used for the success URL (GET or POST)'
                  example: ''
                pg_failure_url_method:
                  description: '* Method used for the failure URL (GET or POST)'
                  example: ''
                  type: string
                pg_request_method:
                  type: integer
                  description: '* GET'
                  example: ''
                pg_param1:
                  description: '* Additional parameter 1'
                  example: ''
                  type: string
                pg_param2:
                  description: '* Additional parameter 2'
                  example: ''
                  type: string
                pg_param3:
                  description: '* Additional parameter 3'
                  example: ''
                  type: string
                pg_generate_qr:
                  description: >-
                    * Receive a QR code with a link to the payment form in
                    base64 format
                  example: ''
                  type: boolean
                pg_idempotency_key:
                  description: >-
                    * Idempotency key. Used to prevent duplicate request
                    creation. A unique value within the merchant's scope; the
                    same key cannot be used for different operations
                  example: ''
                  type: string
                pg_loyalty_id:
                  description: '* Identifier in the loyalty system'
                  example: ''
                  type: string
                pg_loyalty_amount:
                  description: '* Amount of accrued units in the loyalty system'
                  example: 0
                  type: number
                pg_freedom_id:
                  description: '* User identifier in the Freedom ecosystem'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_description
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: Payment ID
                  pg_status:
                    type: string
                    description: ok
                  pg_redirect_url:
                    type: string
                  pg_redirect_url_type:
                    type: string
                  pg_redirect_qr:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_redirect_url
                  - pg_redirect_url_type
                  - pg_redirect_qr
                  - pg_salt
                  - pg_sig
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_redirect_url
                  - pg_salt
                  - pg_redirect_qr
                  - pg_redirect_url_type
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>ok</pg_status>
                    <pg_payment_id>123456</pg_payment_id>
                    <pg_redirect_url>https://customer.freedompay.kz/</pg_redirect_url>
                    <pg_redirect_url_type>need data</pg_redirect_url_type>
                    <pg_redirect_qr>data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA...</pg_redirect_qr>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>signature-abc123</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9890672-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Card

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/payment:
    post:
      summary: Card
      deprecated: false
      description: >
        :::info[]

        - This method is used for processing payments using a card

        - At this stage, the payer provides card details to execute the
        transaction

        - The payment can follow two scenarios: with 3D Secure (3DS) or without
        it

        :::


        #### Interaction diagram for non3ds payment

        :::tip[]

        Status: *success/error/pending*

        :::

        ![error Payment
        non3DS.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348608/image-preview)


        #### Interaction diagram for 3ds payment

        :::tip[]

        Status: *success/error*

        :::


        ![error Payment 
        3DS.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348609/image-preview)


        :::tip[]

        Status: *pending*

        :::


        ![G2G_API_V3-pending Payment  3DS. case
        2.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348610/image-preview)
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: number
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                     It is recommended to keep this field unique
                  example: ''
                  type: string
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_currency:
                  description: '* Currency in which the amount is specified'
                  example: ''
                  type: string
                pg_description:
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                  type: string
                pg_testing_mode:
                  type: integer
                  minimum: 0
                  maximum: 1
                  description: >-
                    * Payment mode

                    0 - production, 1 - test. If the mode is not specified, then
                    the mode set in the shop settings is taken
                  example: 0
                pg_user_id:
                  type: string
                  examples:
                    - No65GFR755789T
                  description: >-
                    * User ID in the merchant's system

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                pg_user_email:
                  type: string
                  format: email
                  examples:
                    - example@site.com.
                  description: >-
                    * Payer's email or email linked (specified during
                    registration) to the personal account ID or wallet number of
                    the payer.

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                pg_user_phone:
                  description: >-
                    * Payer's phone number or phone number linked (specified
                    during registration) to the personal account ID or wallet
                    number of the payer.

                    Digits without spaces, plus signs, or parentheses

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                  type: string
                pg_card_pan:
                  type: string
                  minLength: 13
                  maxLength: 20
                  description: '* Card number'
                  example: ''
                pg_card_cvc:
                  type: integer
                  description: '* CVC/CVC2/CVV card password'
                  example: 0
                pg_card_year:
                  type: integer
                  description: '* Card expiration year'
                  example: 0
                pg_card_month:
                  type: integer
                  description: '* Card expiration month'
                  example: 0
                pg_card_name:
                  description: '* Name and surname of card holders'
                  example: John Doe
                  type: string
                pg_auto_clearing:
                  type: boolean
                  description: >-
                    * Clearing type (0 or 1)

                    1 - automatic write-off after successful authorization, 0 -
                    write-off by launching the clearing method
                  example: ''
                pg_3ds_challenge:
                  type: boolean
                  description: >-
                    * Determines the need to complete the Challenge Flow

                    (1 - it is mandatory to conduct the Challenge Requested, 0
                    or empty - the method is determined by the issuer) the
                    issuing bank can ignore this parameter and make a payment
                    according to its own Challenge Flow
                  example: ''
                pg_exchange_params:
                  type: object
                  x-apidog-orders:
                    - rate
                    - rates_code
                    - ex_date
                  properties:
                    rate:
                      type: string
                      description: >-
                        The exchange rate provided by the merchant. Payments
                        will be converted using this exact rate.
                    rates_code:
                      type: string
                      description: >-
                        Unique currency rate source identifier. Contact your
                        account manager to obtain this code.
                    ex_date:
                      type: string
                      description: >-
                        Historical date for applying the exchange rate. If
                        empty, current date applies.
                  description: >-
                    * Exchange rate parameters passed when a fixed rate needs to
                    be used
                  example: ''
                pg_param1:
                  description: '* Additional parameter 1'
                  example: ''
                  type: string
                pg_param2:
                  description: '* Additional parameter 2'
                  example: ''
                  type: string
                pg_param3:
                  description: '* Additional parameter 3'
                  example: ''
                  type: string
                pg_recurring_start:
                  type: integer
                  examples:
                    - 0
                    - 1
                  description: >-
                    Flag that accepts a value of 0 or 1. For detailed
                    information, see the **Recurrent Payments** section. To use
                    this parameter, please contact your account manager.
                  example: 0
                pg_recurring_lifetime:
                  type: integer
                  minimum: 1
                  maximum: 156
                  description: >-
                    The duration for which the merchant intends to use the
                    recurrent payment profile.

                    Minimum allowed value: 1 (1 month).

                    Maximum allowed value: 156 (13 years).
                  example: 0
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
                pg_receipt_positions[0][count]:
                  type: integer
                  minimum: 1
                  description: '* Product quantity'
                  example: 0
                pg_receipt_positions[0][name]:
                  type: string
                  format: char
                  minLength: 1
                  description: '* Product name'
                  example: ''
                pg_receipt_positions[0][price]:
                  type: number
                  minimum: 1
                  maximum: 99999999
                  description: '* Price per unit'
                  example: 0
                pg_receipt_positions[0][tax_type]:
                  type: integer
                  enum:
                    - 0
                    - 3
                    - 7
                    - 11
                  x-apidog-enum:
                    - value: 0
                      name: ''
                      description: Without tax
                    - value: 3
                      name: ''
                      description: VAT 16/116
                    - value: 7
                      name: ''
                      description: VAT 10/110
                    - value: 11
                      name: ''
                      description: VAT 5/105
                  description: '* Tax type'
                  example: 0
                pg_receipt_positions[0][UnitCode]:
                  type: integer
                  description: '* Unit of measurement'
                  example: 0
                pg_receipt_positions[0][GTIN]:
                  description: '* Barcode'
                  example: ''
                  type: string
                pg_receipt_positions[0][NTIN]:
                  description: >-
                    * Barcode assigned to goods by the National Goods Catalog of
                    the Republic of Kazakhstan
                  example: ''
                  type: string
                pg_receipt_positions[0][mark_list][]:
                  type: array
                  items:
                    type: string
                  description: >-
                    Array of marking codes for labeled goods. Number of elements
                    must match the `count` value. 

                    Example: `"mark_list": ["code1"]` for count = 1,
                    `"mark_list": ["code1", "code2"]` for count = 2
                  example: ''
                pg_encrypted_card:
                  description: >-
                    This parameter contains encrypted card data packaged in JWE
                    format. Encryption is performed using a hybrid approach:

                    - card data (PAN, expiration date, CVV2, message creation
                    timestamp) is encrypted using AES-256-GCM

                    - the generated symmetric key (CEK) is encrypted using
                    RSA-OAEP-256 (SHA-256) with the partner’s public key

                    The result is encoded in Base64URL and transmitted as a
                    single encrypted container


                    **Encryption requirements**

                    | Category | Parameter                | Requirement|
                    Description|

                    |------|----------------------------|----------------------------|----------------------------|

                    |     General     |    Encryption Method         |   Ue
                    Hybrid Encryption (Symmetric + Asymmetric)         |  
                    Combines symmetric encryption for payload protection with
                    asymmetric encryption for secure key exchange        |

                    |   Payload Encryption            |   Algorithm          |  
                    Use AES-256-GCM         |  Provides confidentiality and
                    integrity via authenticated encryption         |

                    |  Payload Encryption             |  Content Encryption Key
                    (CEK)          |  Must be 256 bits and generated using
                    CSPRNG          |  Symmetric key used for payload
                    encryption         |

                    |Payload Encryption|Initialization Vector (IV)|Must be 96
                    bits (12 bytes), generated using CSPRNG and must be unique
                    per encryption|Nonce required for AES-GCM to ensure security
                    and prevent reuse attacks |

                    | Payload Encryption              |   Authentication
                    Tag          |  Must be 128 bits and generated during
                    AES-GCM encryption          |  Ensures integrity and
                    authenticity of encrypted data         |

                    | Key Encryption              |  Algorithm           |  Use
                    RSA-OAEP-256          |  Asymmetric encryption of CEK using
                    OAEP padding with SHA-256         |

                    | Key Encryption              |  Public Key           | Use
                    recipient’s RSA public key           | Used to encrypt the
                    CEK         |

                    | Key Encryption              |   RSA Key Length          | 
                    Must be ≥ 2048 bits          |  Ensures sufficient
                    cryptographic strength         |

                    |  Encoding             |   Encoding Scheme          | Use
                    Base64URL (without padding)           | URL-safe encoding
                    for binary data (header, encrypted key, IV, ciphertext,
                    authentication tag)          |


                    **Encryption process** (for sending data)

                    **Step 1.** Prepare payload

                    ```

                    {

                    "pan": "1234567890123456",

                    "expDate": "202802",

                    "cvv2": "123",

                    "timestamp": "20260318123045" 

                    }

                    ```

                    **Step 2.** Generate CEK

                    Generate a random 256-bit key using CSPRNG


                    **Step 3.** Generate IV

                    - Generate 12-byte IV using CSPRNG

                    - Must be unique per encryption


                    **Step 4.** Prepare header

                    ```

                    {

                    "alg": "RSA-OAEP-256",

                    "enc": "A256GCM",

                    "kid": "<key identifier>"

                    }

                    ```


                    **Step 5.** Encrypt payload (AES-256-GCM)

                    - Inputs: CEK, IV, Payload

                    - Outputs: **ciphertext** and **authentication tag**


                    **Step 6.** Encrypt CEK (RSA-OAEP-256)

                    Encrypt CEK using recipient’s public key

                    Output: encrypted_key


                    **Step 7.** Encode components

                    Base64URL encode: header, encrypted_key, IV, ciphertext,
                    authentication tag


                    **Step 8.** Build encrypted container

                    After all components are generated, the encrypted container
                    must be constructed according to JSON Web Encryption (JWE)
                    RFC 7516 using **Compact Serialization**.

                    BASE64URL(Protected Header) .

                    BASE64URL(Encrypted Key) .

                    BASE64URL(IV) .

                    BASE64URL(Ciphertext) .

                    BASE64URL(Authentication Tag)

                    ```|``` The serialization order is strictly defined by the
                    JWE specification and must be preserved. 

                    Example:

                    ```

                    eyJhbGciOiJSU0EtT0FFUC0yNTYiLCJlbmMiOiJBMjU2R0NNIiwia2lkIjoiNzYxYSJ9

                    .

                    OKOawDo13gRp2ojaHV7LFp...

                    .

                    48V1_ALb6US04U3b

                    .

                    5eym8TW_c8SuK0ltJ3rpYIzO...

                    .

                    XFBoMYUZodetZdvTiFvSkQ

                    ```


                    **Decryption process** (for receiving data)

                    **Step 1.** Split Encrypted Container

                    The input parameter pg_encrypted_card must be a JWE Compact
                    Serialization string compliant with JSON Web Encryption
                    (JWE) RFC 7516. Split into exactly **5 parts** using the
                    ```.``` (dot) separator:

                    ```

                    <protected_header> .


                    <encrypted_key> .


                    <iv> .


                    <ciphertext> .


                    <authentication_tag>

                    ```


                    Output Components: after splitting, the following components
                    are obtained:

                    | Component               | Description|

                    |------|----------------------------|

                    | Protected Header   | Base64URL-encoded JSON containing
                    metadata about encryption algorithms and key identifier    
                    |

                    | Encrypted Key   | Base64URL-encoded CEK encrypted using
                    RSA-OAEP-256     |

                    | Initialization Vector (IV)   | Base64URL-encoded 96-bit
                    nonce used in AES-GCM     |

                    | Ciphertext   | Base64URL-encoded encrypted payload     |

                    | Authentication Tag   | Base64URL-encoded
                    integrity/authentication tag generated by AES-GCM     |


                    **Step 2.** Base64URL decode

                    Each component must be decoded from Base64URL encoding to
                    its original binary form:

                    - protected_header → JSON (UTF-8)

                    - encrypted_key → binary (RSA-encrypted CEK)

                    - iv → binary (12 bytes)

                    - ciphertext → binary

                    - authentication_tag → binary (16 bytes)


                    **Step 3.** Parse and validate protected header

                    The protected header must be parsed as JSON:

                    ```

                    {

                    "alg": "RSA-OAEP-256",

                    "enc": "A256GCM",

                    "kid": "<key identifier>"

                    }

                    ```


                    Extracted Parameters

                    | Field               | Description|

                    |------|----------------------------|

                    | alg     | Key encryption algorithm (RSA-OAEP-256)        |

                    |  enc    |  Content encryption algorithm (A256GCM)       |

                    | kid     |  Key identifier used to select the correct
                    decryption key       |


                    ```|``` If validation fails, processing will be terminated.


                    **Step 4.** Decrypt CEK (Content Encryption Key)

                    The encrypted_key must be decrypted using:

                    - Algorithm: RSA-OAEP-256

                    - Hash function: SHA-256

                    - Key: recipient’s private RSA key (selected via kid)


                    Output: Original CEK (256-bit AES key)


                    **Step 5.** Decrypt Payload (AES-256-GCM)

                    The payload will be decrypted using:

                    - Algorithm: AES-256-GCM

                    - Inputs: CEK, IV, ciphertext, authentication_tag


                    ```|``` If verification fails, the message will be rejected
                    and will not be processed further.

                    - Output: Decrypted payload (JSON)


                    **Step 6.** Parse Decrypted Payload

                    The decrypted payload will be parsed as JSON:

                    ```

                    {

                    "pan": "1234567890123456",

                    "expDate": "202802",

                    "cvv2": "123",

                    "timestamp": "YYYYMMDDHHMMSS"

                    }

                    ```
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_card_pan
                - pg_card_cvc
                - pg_card_year
                - pg_card_month
                - pg_card_name
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: string
                    description: Transaction ID
                  pg_status:
                    type: string
                    description: Request status
                  pg_3ds:
                    type: boolean
                    description: |-
                      Flag indicating the need for a 3DS request.
                      1 – 3DS is required, 0 - not required
                  pg_auth_code:
                    type: string
                    description: Payment authorization code from the bank
                  pg_reference:
                    type: string
                    description: Transaction reference
                  pg_datetime:
                    type: string
                    description: "Date and time of the request\t"
                  pg_salt:
                    type: string
                    description: Random string
                  pg_sig:
                    type: string
                    description: "Request digital signature\t"
                  pg_3d_md:
                    type: string
                    description: Card Issuer Bank Url for 3ds Validation
                  pg_3d_acsurl:
                    type: string
                    description: Parameter for request 3ds
                  pg_3d_pareq:
                    type: string
                    description: "Parameter for request 3ds\t"
                  pg_card_id:
                    type: integer
                    description: "Saved card ID for next payments (Deprecated)\t"
                  pg_card_token_to:
                    type: string
                    description: "Saved card token for next payments\t"
                  pg_recurring_profile:
                    type: integer
                    description: >-
                      Recurring profile ID (if the payment request parameter
                      pg_recurring_start = 1 was specified)
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_3d_md
                  - pg_3d_acsurl
                  - pg_3d_pareq
                  - pg_auth_code
                  - pg_reference
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                  - pg_card_id
                  - pg_card_token_to
                  - pg_recurring_profile
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_auth_code
                  - pg_reference
                  - pg_datetime
                  - pg_salt
                  - pg_sig
              examples:
                '1':
                  summary: Success
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_payment_id>7777777777</pg_payment_id>
                        <pg_status>ok</pg_status>
                        <pg_3ds>0</pg_3ds>
                        <pg_auth_code/>
                        <pg_reference/>
                        <pg_datetime>2024-09-02T12:19:01+00:00</pg_datetime>
                        <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                        <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    </response>
                '2':
                  summary: Process
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_payment_id>7777777777</pg_payment_id>
                        <pg_status>pending</pg_status>
                        <pg_3ds>0</pg_3ds>
                        <pg_datetime>2024-11-07T06:31:04+00:00</pg_datetime>
                        <pg_salt>7x6lXSsN9MyzwpnU</pg_salt>
                        <pg_sig>e4798ffe3958c001ed9d43269a20d931</pg_sig>
                    </response>
                '3':
                  summary: Invalid Signature
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>1100</pg_error_code>
                        <pg_error_description>Некорректная подпись запроса</pg_error_description>
                        <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                        <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                        <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                    </response>
                '4':
                  summary: Error
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>9999</pg_error_code>
                        <pg_error_description>ERROR_MESSAGE</pg_error_description>
                        <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                        <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                        <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Process:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: string
                    description: Transaction ID
                  pg_status:
                    type: string
                    description: Request status
                  pg_3ds:
                    type: boolean
                    description: |-
                      Flag indicating the need for a 3DS request.
                      1 – 3DS is required, 0 - not required
                  pg_datetime:
                    type: string
                    description: "Date and time of the request\t"
                  pg_salt:
                    type: string
                    description: Random string
                  pg_sig:
                    type: string
                    description: "Request digital signature\t"
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                  - pg_3ds
          headers: {}
          x-apidog-name: Process
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Request status
                  pg_error_code:
                    type: integer
                    description: "Error code ID\t"
                  pg_error_description:
                    type: string
                    description: Text description of the error
                  pg_datetime:
                    type: string
                    description: Date and time of the request
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: "Request digital signature\t"
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Invalid Signature
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Request status
                  pg_error_code:
                    type: integer
                    description: "Error code ID\t"
                  pg_error_description:
                    type: string
                    description: Text description of the error
                  pg_datetime:
                    type: string
                    description: Date and time of the request
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: "Request digital signature\t"
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Error
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9586997-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# 3DSecure

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/paymentAcs:
    post:
      summary: 3DSecure
      deprecated: false
      description: >-
        :::info[]

        - When using this method, 3ds is required, therefore it is necessary to
        make a request to the ACS server of the card issuer bank

        - 3D Secure (3DS) is an authentication technology to protect against
        unauthorized use of cards. It allows for verifying the cardholder’s
        identity before the payment is processed

        - The authentication process works as follows: after entering the card
        details, the issuer’s website opens, prompting the cardholder to enter a
        password or secret code. The code is usually sent via SMS. If the code
        is entered correctly, the payment is authorized; if not, the transaction
        is declined

        - 3D Secure is available only for cards issued by banks that support
        this technology. Payments without 3D Secure are considered less secure

        :::
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_md:
                  description: |-
                    * Parameter from the response
                    ACS server of the issuer.
                  example: ''
                  type: string
                pg_pares:
                  description: |-
                    * Parameter from response
                    ACS server of the issuer
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_md
                - pg_pares
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: Transaction ID
                  pg_status:
                    type: string
                    description: Request status
                  pg_card_id:
                    type: integer
                    description: >-
                      ID of the stored card for future payments (if card storage
                      parameters pg_save_card and pg_user_id were specified).
                      Deprecated
                  pg_auth_code:
                    type: string
                    description: "Payment authorization code from the bank\t"
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: "Digital signature of the request\t"
                  "pg_card_token\t":
                    type: string
                    description: >-
                      Saved card token for next payment. (if card storage
                      parameters pg_save_card and pg_user_id were specified)
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_auth_code
                  - pg_salt
                  - pg_sig
                  - pg_card_id
                  - "pg_card_token\t"
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_auth_code
                  - pg_salt
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7999007771</pg_payment_id>
                    <pg_status>ok</pg_status>
                    <pg_auth_code>243412</pg_auth_code>
                    <pg_reference>241107063029</pg_reference>
                    <pg_datetime>2024-11-07T06:30:29+00:00</pg_datetime>
                    <pg_salt>Lc9M2TKR79VVNEc4</pg_salt>
                    <pg_sig>91c6f70ea9e20db854a61b0c90c6ae9c</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Request status
                  pg_error_code:
                    type: integer
                    description: "Error code ID\t"
                  pg_error_description:
                    type: string
                    description: "Text description of the error\t"
                  pg_datetime:
                    type: string
                    description: "Date and time of the request\t"
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: "Request digital signature\t"
                  pg_payment_id:
                    type: string
                    description: |-
                      Transaction ID
                      * Optional
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                  - pg_payment_id
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>9999</pg_error_code>
                    <pg_error_description>ERROR_MESSAGE</pg_error_description>
                    <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                    <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                    <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Request status
                  pg_error_code:
                    type: integer
                    description: "Error code ID\t"
                  pg_error_description:
                    type: string
                    description: "Text description of the error\t"
                  pg_datetime:
                    type: string
                    description: "Date and time of the request\t"
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: "Request digital signature\t"
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9586999-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Recurrent

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/recurrent:
    post:
      summary: Recurrent
      deprecated: false
      description: ''
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_amount:
                  type: number
                  description: Payment amount
                  example: 100
                pg_description:
                  description: Payment description
                  example: ''
                  type: string
                pg_merchant_id:
                  type: number
                  description: Merchant ID
                  example: 0
                pg_order_id:
                  description: ID in the merchant system
                  example: ''
                  type: string
                pg_recurring_profile:
                  type: number
                  description: Recurrent profile ID
                  example: 0
                pg_salt:
                  description: >-
                    Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: Request signature
                  example: ''
                  type: string
              required:
                - pg_amount
                - pg_description
                - pg_merchant_id
                - pg_order_id
                - pg_recurring_profile
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: string
                    description: Payment ID
                  pg_status:
                    type: string
                    description: Request status
                  pg_recurring_profile:
                    type: string
                    description: Recurrent profile ID
                  pg_datetime:
                    type: string
                    description: Datetime
                  pg_salt:
                    type: string
                    description: >-
                      Random string consisting of arbitrary numbers and Latin
                      letters
                  pg_sig:
                    type: string
                    description: Request signature
                  01JYNKGA6SYZNQMT50CKF6WJ9D:
                    type: string
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_recurring_profile
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                  - 01JYNKGA6SYZNQMT50CKF6WJ9D
                xml:
                  name: response
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_recurring_profile
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                  - 01JYNKGA6SYZNQMT50CKF6WJ9D
              example: "<?xml version=\"1.0\" encoding=\"utf-8\"?>\r\n<response>\r\n    <pg_payment_id>1585424243</pg_payment_id>\r\n    <pg_status>ok</pg_status>\r\n    <pg_recurring_profile>60144557</pg_recurring_profile>\r\n    <pg_datetime>2025-06-26T07:50:54+00:00</pg_datetime>\r\n    <pg_salt>9nuHfolL76qs94Br</pg_salt>\r\n    <pg_sig>b3165b66f43d7985db0bc60dc2951898</pg_sig>\r\n</response>"
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-18494941-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Cancel

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/cancel:
    post:
      summary: Cancel
      deprecated: false
      description: >-
        :::info[]

        - Cancel payment before the actual fund withdrawal is available only for
        a *two-step* payment process

        - Payment cancellation is made before funds are debited, at the stage of
        holding the amount on the payer's card

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error/pending*

        :::


        ![image.png](https://api.apidog.com/api/v1/projects/640842/resources/348613/image-preview)
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
                pg_receipt_positions[0][count]:
                  type: integer
                  minimum: 1
                  description: '* Product quantity'
                  example: 0
                pg_receipt_positions[0][name]:
                  type: string
                  format: char
                  minLength: 1
                  description: '* Product name'
                  example: ''
                pg_receipt_positions[0][price]:
                  type: number
                  minimum: 1
                  multipleOf: 99999999
                  description: '* Price per unit'
                  example: 0
                pg_receipt_positions[0][tax_type]:
                  type: integer
                  enum:
                    - 0
                    - 3
                    - 7
                    - 11
                  x-apidog-enum:
                    - value: 0
                      name: ''
                      description: Without tax
                    - value: 3
                      name: ''
                      description: VAT 16/116
                    - value: 7
                      name: ''
                      description: VAT 10/110
                    - value: 11
                      name: ''
                      description: VAT 5/105
                  description: '* Tax type'
                  example: 0
                pg_receipt_positions[0][UnitCode]:
                  type: integer
                  description: '* Unit of measurement'
                  example: 0
                pg_receipt_positions[0][GTIN]:
                  description: '* Barcode'
                  example: ''
                  type: string
                pg_receipt_positions[0][NTIN]:
                  description: >-
                    * Barcode assigned to goods by the National Goods Catalog of
                    the Republic of Kazakhstan
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: "Transaction ID\t"
                  pg_payment_revoke_id:
                    type: integer
                    description: "Cancellation transaction ID\t"
                  pg_status:
                    type: string
                    description: "Request status\t"
                  pg_revoke_status:
                    type: string
                    description: "Payment cancellation status\t"
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: Digital signature of the request
                x-apidog-orders:
                  - pg_payment_id
                  - pg_payment_revoke_id
                  - pg_status
                  - pg_revoke_status
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_payment_revoke_id
                  - pg_status
                  - pg_revoke_status
                  - pg_salt
                  - pg_sig
              examples:
                '1':
                  summary: Success
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_payment_id>7777777777</pg_payment_id>
                        <pg_payment_revoke_id>7777777778</pg_payment_revoke_id>
                        <pg_status>ok</pg_status>
                        <pg_revoke_status>success</pg_revoke_status>
                        <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                        <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    </response>
                '2':
                  summary: Error
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>9999</pg_error_code>
                        <pg_error_description>ERROR_MESSAGE</pg_error_description>
                        <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                        <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                        <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                    </response>
                '3':
                  summary: Invalid Signature
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>1100</pg_error_code>
                        <pg_error_description>Некорректная подпись запроса</pg_error_description>
                        <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                        <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                        <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587002-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Clearing

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/clearing:
    post:
      summary: Clearing
      deprecated: false
      description: >-
        :::info[]

        - This method involves sending a request to withdraw the payment amount
        that was previously held on the payer's card

        - If Freedom Pay Gateway does not receive a clearing or cancellation
        request within 5 days, the payment will be automatically cleared

        - The method is available only for *two-step* payments

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error/pending*

        :::


        ![G2G_API_V3-Clearing.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348614/image-preview)
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_clearing_amount:
                  type: number
                  description: >-
                    * The partial clearing amount should be less than the
                    payment amount
                  example: 0
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: '* Transaction ID. '
                  pg_amount:
                    type: integer
                    description: '* Total amount.'
                  pg_clearing_amount:
                    type: integer
                    description: >-
                      * The partial clearing amount should be less than the
                      payment amount.
                  pg_status:
                    type: string
                    description: Request status
                  pg_clearing_status:
                    type: string
                    description: |-
                      Clearing status. 
                      1 - Clearing completed, 0 - Clearing not completed
                  pg_salt:
                    type: string
                    description: |-
                      Random string.
                      Arbitrary digits and Latin letters
                  pg_sig:
                    type: string
                    description: Digital signature of the request.
                x-apidog-orders:
                  - pg_payment_id
                  - pg_amount
                  - pg_clearing_amount
                  - pg_status
                  - pg_clearing_status
                  - pg_salt
                  - pg_sig
                xml: {}
                required:
                  - pg_payment_id
                  - pg_amount
                  - pg_clearing_amount
                  - pg_status
                  - pg_clearing_status
                  - pg_salt
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_amount>1000</pg_amount>
                    <pg_clearing_amount>500</pg_clearing_amount>
                    <pg_status>ok</pg_status>
                    <pg_status_clearing>1</pg_status_clearing>
                    <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>9999</pg_error_code>
                    <pg_error_description>ERROR_MESSAGE</pg_error_description>
                    <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                    <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                    <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587001-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Refund

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/refund:
    post:
      summary: Refund
      deprecated: false
      description: >-
        :::info[]

        - Refund is a method used to return funds to the payer for a previously
        processed payment

        - It is applicable only in cases where the funds have already been
        withdrawn from the payer's card

        - This method is available for *one-step payments and already cleared
        two-step payments* but cannot be used for *two-step payments that have
        not been cleared*

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error/pending*

        :::


        ![G2G_API_V3-Refund of deducted
        payment.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348615/image-preview)
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  format: slslslsls
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Return amount in pg_currency'
                  example: 0
                pg_currency:
                  description: '* Debit currency in which the amount is specified'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
                pg_receipt_positions[0][count]:
                  type: integer
                  minimum: 1
                  description: '* Product quantity'
                  example: 0
                pg_receipt_positions[0][name]:
                  type: string
                  format: char
                  minLength: 1
                  description: '* Product name'
                  example: ''
                pg_receipt_positions[0][price]:
                  type: number
                  minimum: 1
                  maximum: 99999999
                  description: '* Price per unit'
                  example: 0
                pg_receipt_positions[0][tax_type]:
                  type: integer
                  enum:
                    - 0
                    - 3
                    - 7
                    - 11
                  x-apidog-enum:
                    - value: 0
                      name: ''
                      description: Without tax
                    - value: 3
                      name: ''
                      description: VAT 16/116
                    - value: 7
                      name: ''
                      description: VAT 10/110
                    - value: 11
                      name: ''
                      description: VAT 5/105
                  description: '* Tax type'
                  example: 0
                pg_receipt_positions[0][UnitCode]:
                  type: integer
                  description: '* Unit of measurement'
                  example: 0
                pg_receipt_positions[0][GTIN]:
                  description: '* Barcode'
                  example: ''
                  type: string
                pg_receipt_positions[0][NTIN]:
                  description: >-
                    * Barcode assigned to goods by the National Goods Catalog of
                    the Republic of Kazakhstan
                  example: ''
                  type: string
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: "Transaction ID\t"
                  pg_status:
                    type: string
                    description: "Request status\t"
                  pg_salt:
                    type: string
                    description: "Random string\t"
                  pg_sig:
                    type: string
                    description: Digital signature of the request
                  pg_payment_refund_id:
                    type: integer
                    description: "Refund transaction ID\t"
                  pg_refund_status:
                    type: string
                    description: "Payment refund status\t"
                x-apidog-orders:
                  - pg_payment_id
                  - pg_payment_refund_id
                  - pg_status
                  - pg_refund_status
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_payment_refund_id
                  - pg_status
                  - pg_refund_status
                  - pg_salt
                  - pg_sig
              examples:
                '1':
                  summary: Success
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_payment_id>7777777777</pg_payment_id>
                        <pg_payment_refund_id>7777777778</pg_payment_refund_id>
                        <pg_status>ok</pg_status>
                        <pg_refund_status>success</pg_refund_status>
                        <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                        <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    </response>
                '2':
                  summary: Error
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>9999</pg_error_code>
                        <pg_error_description>ERROR_MESSAGE</pg_error_description>
                        <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                        <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                        <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                    </response>
                '3':
                  summary: Invalid Signature
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>1100</pg_error_code>
                        <pg_error_description>Некорректная подпись запроса</pg_error_description>
                        <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                        <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                        <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587003-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Status

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/status_v2:
    post:
      summary: Status
      deprecated: false
      description: >-
        :::info[]

        This method is used to get information about the current status of a
        payment, such as whether it was successful, an error occurred, or is
        pending

        :::
      tags:
        - Gateway API/Sync API/Purchase
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_order_id:
                  description: '* Payment ID in the merchant system'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_order_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: number
                    description: Transaction ID
                  pg_order_id:
                    type: string
                    description: Order ID in the shop system
                    pattern: ^[a-zA-Z0-9]+$
                  pg_currency:
                    type: string
                    description: 'Payment currency. Example: KZT'
                  pg_status:
                    type: string
                    description: Request status. Latin characters only.
                  pg_payment_status:
                    type: string
                    description: Payment status. Latin characters only.
                  pg_amount:
                    type: number
                    description: Amount displayed in the payment
                  pg_clearing_amount:
                    type: number
                    description: Amount written off during payment clearing
                  pg_refund_amount:
                    type: number
                    description: Refunded amount
                  pg_user_email:
                    type: string
                    format: email
                    description: Payer's e-mail
                  pg_card_name:
                    type: string
                    description: Payer's name
                  pg_card_id:
                    type: number
                    description: >-
                      Card ID for paying with saved card (Deprecated). Example:
                      1234
                  pg_card_token:
                    type: string
                    description: >-
                      Card token for paying with saved card. Example:
                      ef741cfc-f85e-41a0-84e6-2ba964912182
                  pg_card_pan:
                    type: string
                    description: 'Masked card number. Example: 5483-18XX-XXXX-0293'
                  pg_card_exp:
                    type: string
                    description: 'Card Expiration Date. Example: 03/23'
                  pg_card_brand:
                    type: string
                    description: 'Card brand code. Example: VI'
                  pg_user_phone:
                    type: string
                    description: 'Payer''s phone number. Format: 77001234567'
                  pg_payment_date:
                    type: string
                    format: date-time
                    description: 'Payment date. Format: YYYY-MM-DD hh:mm:ss'
                  pg_captured:
                    type: number
                    description: >-
                      Flag indicating whether the write-off (clearing) of the
                      payment has passed. Values: 0 or 1
                  pg_refund_payments:
                    type: array
                    description: List of refunds for this payment
                    items:
                      type: object
                      properties:
                        pg_payment_id:
                          type: number
                          description: Transaction ID
                        pg_payment_status:
                          type: string
                          description: Payment status. Latin characters only.
                        pg_amount:
                          type: number
                          description: Amount set for refund
                        pg_payment_date:
                          type: string
                          format: date-time
                          description: >-
                            Payment date. Only successful returns have it.
                            Format: YYYY-MM-DD hh:mm:ss
                        pg_reference:
                          type: string
                          description: >-
                            Bank-Assigned Unique Bank Transaction Identifier
                            (RRN)
                        pg_failure_code:
                          type: number
                          description: >-
                            Return error code. Available only for returns with
                            the status 'error'.
                        pg_failure_description:
                          type: string
                          description: >-
                            Description of the return error. Only returns with
                            status 'error'.
                      x-apidog-orders:
                        - pg_payment_id
                        - pg_payment_status
                        - pg_amount
                        - pg_payment_date
                        - pg_reference
                        - pg_failure_code
                        - pg_failure_description
                  pg_revoked_payments:
                    type: array
                    description: List of revokes for this payment
                    items:
                      type: object
                      properties:
                        pg_payment_id:
                          type: number
                          description: Revoke transaction ID
                        pg_payment_status:
                          type: string
                          description: Revoke payment status. Latin characters only.
                      x-apidog-orders:
                        - pg_payment_id
                        - pg_payment_status
                  pg_reference:
                    type: string
                    description: >-
                      A unique bank transaction identifier assigned by the bank
                      (RRN)
                  pg_intreference:
                    type: string
                    description: >-
                      A unique bank transaction identifier assigned by the bank
                      (ARN)
                  pg_failure_code:
                    type: number
                    description: >-
                      Return error code. Only available for returns with 'error'
                      status.
                  pg_failure_description:
                    type: string
                    description: >-
                      Description of the return error. Available only for
                      returns with the status 'error'.
                  pg_auth_code:
                    type: string
                    description: Bank payment authorization code. Digits, length 6.
                  pg_salt:
                    type: string
                    description: Random string. Arbitrary numbers and Latin letters.
                  pg_sig:
                    type: string
                    description: Request digital signature. Numbers and Latin letters.
                  pg_datetime:
                    type: string
                    format: date-time
                    description: >-
                      Date and time of the request. Format:
                      YYYY-MM-DDThh:mm:ss±hh:mm.
                required:
                  - pg_payment_id
                  - pg_order_id
                  - pg_currency
                  - pg_status
                  - pg_amount
                  - pg_user_email
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                x-apidog-orders:
                  - pg_payment_id
                  - pg_order_id
                  - pg_currency
                  - pg_status
                  - pg_payment_status
                  - pg_amount
                  - pg_clearing_amount
                  - pg_refund_amount
                  - pg_user_email
                  - pg_card_name
                  - pg_card_id
                  - pg_card_token
                  - pg_card_pan
                  - pg_card_exp
                  - pg_card_brand
                  - pg_user_phone
                  - pg_payment_date
                  - pg_captured
                  - pg_refund_payments
                  - pg_revoked_payments
                  - pg_reference
                  - pg_intreference
                  - pg_failure_code
                  - pg_failure_description
                  - pg_auth_code
                  - pg_salt
                  - pg_sig
                  - pg_datetime
              examples:
                '1':
                  summary: Success
                  value: |-
                    <?xml version="1.0" encoding="UTF-8"?>
                    <response>
                      <pg_payment_id>1427057029</pg_payment_id>
                      <pg_order_id>2343253465454</pg_order_id>
                      <pg_currency>KZT</pg_currency>
                      <pg_status>ok</pg_status>
                      <pg_payment_status>success</pg_payment_status>
                      <pg_amount>1030</pg_amount>
                      <pg_clearing_amount>0</pg_clearing_amount>
                      <pg_refund_amount>0</pg_refund_amount>
                      <pg_user_email></pg_user_email>
                      <pg_card_name>NAME NAME</pg_card_name>
                      <pg_user_phone></pg_user_phone>
                      <pg_payment_date>2024-11-28 15:44:53</pg_payment_date>
                      <pg_card_pan>4400-44XX-XXXX-4444</pg_card_pan>
                      <pg_card_exp>12/24</pg_card_exp>
                      <pg_card_brand>string</pg_card_brand>
                      <pg_net_amount>1005.28</pg_net_amount>
                      <pg_reference>4333333333</pg_reference>
                      <pg_captured>0</pg_captured>
                      <pg_auth_code>932495</pg_auth_code>
                      <pg_intreference>TE5XTR4GGFF</pg_intreference>
                      <pg_salt>XeFNeRYiwcqlWPg9TZUj6pc9gj6KYBSb</pg_salt>
                      <pg_sig>d333fb3333b3f6e861c61682ba173c46</pg_sig>
                      <pg_datetime>2024-11-28T10:44:55+00:00</pg_datetime>
                    </response>
                '2':
                  summary: Error
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>9999</pg_error_code>
                        <pg_error_description>ERROR_MESSAGE</pg_error_description>
                        <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                        <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Error
        x-200:OK:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Status of request.
                  pg_error_code:
                    type: integer
                    description: 'Error code identifying the specific issue. '
                  pg_error_description:
                    type: string
                    description: Explanation of the error.
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
              example: "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<response>\r\n    <pg_status>error</pg_status>\r\n    <pg_error_code>11068</pg_error_code>\r\n    <pg_error_description>Payment not found.</pg_error_description>\r\n</response>"
          headers: {}
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Sync API/Purchase
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587004-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```
# Overview

### Payout
&emsp;Payout is a payment type which uses one request to make a one-time transfer of funds from merchant to customer.
&emsp;The following sections discuss in more detail which methods are available for making payments.

---
### Available statuses
:::warning[]
Watch out! The diagram will be coming soon!
:::



# Card

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/p2p2nonreg:
    post:
      summary: Card
      deprecated: false
      description: >-
        :::info[]

        - This method uses card number for payout

        - The payment is made directly to the recipient's bank card using its
        number. This method is used for reward payouts, compensations, or other
        financial transactions involving transfers to individuals

        :::


        #### Interaction diagram 

        :::tip[]

        Status: *success/error/pending*

        :::


        ![error.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348616/image-preview)
      tags:
        - Gateway API/Sync API/Payout
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: ''
                  type: string
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                    It is recommended to keep this field unique
                  example: ''
                  type: string
                pg_amount:
                  type: number
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_currency:
                  description: '* Currency in which the amount is specified'
                  example: ''
                  type: string
                pg_description:
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                  type: string
                pg_user_id:
                  description: '* User ID in the merchant system'
                  example: ''
                  type: string
                pg_payment_to:
                  type: integer
                  minimum: 13
                  maximum: 20
                  description: '* Recipient''s card number'
                  example: 0
                pg_card_name:
                  description: '* Name and surname of card holder'
                  example: John Doe
                  type: string
                pg_post_link:
                  description: '* URL to which payment status response is sent'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_payment_to
                - pg_post_link
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_merchant_id:
                    type: integer
                  pg_order_id:
                    type: string
                  pg_status:
                    type: string
                  pg_balance:
                    type: number
                  pg_payment_amount:
                    type: number
                  pg_payment_date:
                    type: object
                    properties: {}
                    x-apidog-orders: []
                  pg_salt:
                    type: string
                  pg_reference:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_merchant_id
                  - pg_order_id
                  - pg_status
                  - pg_balance
                  - pg_payment_amount
                  - pg_reference
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_merchant_id
                  - pg_payment_amount
                  - pg_balance
                  - pg_status
                  - pg_order_id
                  - pg_payment_date
                  - pg_salt
                  - pg_reference
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_merchant_id>9970</pg_merchant_id>
                    <pg_order_id>ORD12345</pg_order_id>
                    <pg_status>ok</pg_status>
                    <pg_balance>500000</pg_balance>
                    <pg_payment_amount>1000</pg_payment_amount>
                    <pg_payment_date>2024-09-02T12:19:01+00:00</pg_payment_date>
                    <pg_reference>FSDUNJFA244324</pg_reference>
                    <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    <pg_datetime>2024-09-02T12:19:01+00:00</pg_datetime>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>9999</pg_error_code>
                    <pg_error_description>ERROR_MESSAGE</pg_error_description>
                    <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                    <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                    <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Payout
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9586998-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# IBAN

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/to_iban:
    post:
      summary: IBAN
      deprecated: false
      description: >-
        :::info[]

        - This method uses the recipient's International Bank Account Number
        (IBAN)

        - IBAN is a standardized account format that ensures accurate
        identification of the recipient's bank and account in both international
        and domestic transactions

        :::


        #### Interaction diagram 

        :::tip[]

        *Status: success/error/pending*

        :::


        ![error.drawio1.png](https://api.apidog.com/api/v1/projects/640842/resources/348618/image-preview)
      tags:
        - Gateway API/Sync API/Payout
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_order_id:
                  type: number
                  description: |-
                    * Payment ID in the merchant system
                    It is recommended to keep this field unique
                  example: 0
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount'
                  example: 0
                pg_description:
                  description: '* Payment description'
                  example: ''
                  type: string
                pg_recipient_iban:
                  type: integer
                  description: '* IBAN account number'
                  example: ''
                pg_recipient_iin:
                  description: '* Recipient IIN'
                  example: ''
                  type: string
                pg_recipient_name:
                  description: '* Recipient name'
                  example: ''
                  type: string
                pg_recipient_kbe:
                  description: '* Recipient kbe'
                  example: 0
                  type: integer
                pg_knp:
                  description: '* Receiver''s KNP'
                  example: 0
                  type: integer
                pg_bank_bik:
                  description: '* Receiver''s BIC'
                  example: ''
                  type: string
                pg_post_link:
                  description: '* URL to which payment status response is sent'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_recipient_iban
                - pg_recipient_iin
                - pg_recipient_name
                - pg_recipient_kbe
                - pg_knp
                - pg_bank_bik
                - pg_post_link
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_merchant_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_merchant_id
                  - pg_status
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                required:
                  - pg_payment_id
                  - pg_salt
                  - pg_payment_date
                  - pg_payment_amount
                  - pg_order_id
                  - pg_merchant_id
                  - pg_status
                  - pg_sig
                  - pg_datetime
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_merchant_id>9970</pg_merchant_id>
                    <pg_status>ok</pg_status>
                    <pg_order_id>ORD12345</pg_order_id>
                    <pg_payment_amount>1000</pg_payment_amount>
                    <pg_payment_date>2024-09-02T12:19:01+00:00</pg_payment_date>
                    <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    <pg_datetime>2024-09-02T12:19:01+00:00</pg_datetime>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>9999</pg_error_code>
                    <pg_error_description>ERROR_MESSAGE</pg_error_description>
                    <pg_datetime>2024-10-07T09:32:21+00:00</pg_datetime>
                    <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                    <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Payout
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9880408-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Balance

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/balance_status:
    post:
      summary: Balance
      deprecated: false
      description: >-
        :::info[]

        This method allows retrieving information about the current state of the
        payout balance

        :::


        #### Interaction diagram

        :::tip[]

        *Status: success/error/pending*

        :::


        ![G2G_API_V3-Get payout
        balance.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348619/image-preview)
      tags:
        - Gateway API/Sync API/Payout
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_currency:
                  description: |-
                    * Balance currency
                    See section Currencies directory
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_currency
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_balance:
                    type: number
                  pg_status:
                    type: string
                  pg_currency:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_balance
                  - pg_status
                  - pg_currency
                  - pg_salt
                  - pg_sig
                required:
                  - pg_balance
                  - pg_status
                  - pg_currency
                  - pg_salt
                  - pg_sig
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_balance>150000.50</pg_balance>
                    <pg_status>ok</pg_status>
                    <pg_currency>KZT</pg_currency>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>signature-abc123</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Payout
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9884858-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Status

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/payout_status2:
    post:
      summary: Status
      deprecated: false
      description: >-
        :::info[]

        This method is used to get information about the current status of a
        payout, such as whether it was successful, an error occurred, or is
        pending

        :::
      tags:
        - Gateway API/Sync API/Payout
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: ''
                  type: string
                pg_payment_id:
                  description: '* Transaction ID'
                  example: ''
                  type: string
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                    It is recommended to keep this field unique
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_order_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_merchant_id:
                    type: integer
                  pg_payment_status:
                    type: string
                  pg_status:
                    type: string
                  pg_order_id:
                    type: string
                  pg_amount:
                    type: number
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                  pg_net_amount:
                    type: integer
                x-apidog-orders:
                  - pg_payment_id
                  - pg_merchant_id
                  - pg_payment_status
                  - pg_status
                  - pg_order_id
                  - pg_net_amount
                  - pg_amount
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                required:
                  - pg_payment_id
                  - pg_salt
                  - pg_amount
                  - pg_order_id
                  - pg_status
                  - pg_payment_status
                  - pg_merchant_id
                  - pg_sig
                  - pg_datetime
                  - pg_net_amount
              example: |-
                <?xml version="1.0" encoding="UTF-8"?>
                <response>
                    <pg_merchant_id>9970</pg_merchant_id>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_status>ok</pg_status>
                    <pg_payment_status>success</pg_payment_status>
                    <pg_order_id>12345</pg_order_id>
                    <pg_amount>13441.5</pg_amount>
                    <pg_net_amount>13441.5</pg_net_amount>
                    <pg_datetime>2024-11-28T11:10:03+00:00</pg_datetime>
                    <pg_salt>FdsmjkonfzxsDF</pg_salt>
                    <pg_sig>cb5a763fb76e05a546nFJJFa13ba27294a</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:OK:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Status of request.
                  pg_error_code:
                    type: integer
                    description: 'Error code identifying the specific issue. '
                  pg_error_description:
                    type: string
                    description: Explanation of the error.
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
              example: "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<response>\r\n    <pg_status>error</pg_status>\r\n    <pg_error_code>11068</pg_error_code>\r\n    <pg_error_description>Payment not found.</pg_error_description>\r\n</response>"
          headers: {}
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Sync API/Payout
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9881016-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Overview

### Money transfer 
:::note[]
Money transfer is a payment type which uses one request to initiate debiting funds from the sender's card and subsequently crediting these funds to the recipient's card
:::

# Card

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/p2p/transfer:
    post:
      summary: Card
      deprecated: false
      description: >-
        :::info[]

        - This method uses card number for transfer

        - The transfer can follow two scenarios: with 3D Secure (3DS) or without
        it

        :::


        :::info[]

        **The special token `2d0b504c-b95d-4cf6-b782-5a7d13ab2c85`** is used to
        indicate which part of the translation should not be performed:

        - If **the special token** is passed in the `pg_card_token` parameter
        and `pg_card_recipient` is provided, only the payout will be processed.
        In this case, one of the parameters (`pg_card_name` or
        `pg_card_recipient_name`) is required

        - If **the special token** is passed in the `pg_card_token` parameter
        and `pg_card_recipient_token` is provided, only the payout will be
        processed

        - If **the special token** is passed in the `pg_card_recipient_token`
        parameter, only the receipt will be processed

        :::


        #### Interaction diagram for non3ds transfer

        :::tip[]

        Status: *success/error/pending*

        :::


        ![G2G_API_V3-Making a transfer (P2P) non
        3DS.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348620/image-preview)
      tags:
        - Gateway API/Sync API/Transfer
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            encoding:
              pg_sig:
                contentType: 'false'
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: ''
                  type: string
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                    It is recommended to keep this field unique
                  example: 0
                  type: integer
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount in pg_currency_from'
                  example: 0
                pg_amount_to:
                  description: '* Payment amount in pg_currency_to'
                  example: 0
                  type: number
                pg_currency_from:
                  description: >-
                    * The debit currency in which the transfer amount is
                    indicated
                  example: ''
                  type: string
                pg_currency_to:
                  description: '* Currency of the transfer'
                  example: ''
                  type: string
                pg_commission_amount:
                  description: '* Commission charged from the payer'
                  example: 0
                  type: number
                pg_description:
                  description: '* Payment description displayed to the buyer'
                  example: ''
                  type: string
                pg_language:
                  description: '* Error text language'
                  example: ''
                  type: string
                pg_user_id:
                  description: '* User ID in the merchant system'
                  example: 0
                  type: integer
                pg_card_token:
                  description: |-
                    * Saved card token of the sender
                    Required if no pg_card_pan
                  example: ''
                  type: string
                pg_card_pan:
                  description: |-
                    * Sender's card number
                    Required if no pg_card_token
                  example: 0
                  type: integer
                pg_card_cvc:
                  description: |-
                    * CVC/CVV card password
                    Required if no pg_card_token
                  example: 0
                  type: integer
                pg_card_year:
                  description: |-
                    * Card expiration year
                    Required if no pg_card_token
                  example: 0
                  type: integer
                pg_card_month:
                  description: |-
                    * Card expiration month
                    Required if no pg_card_token
                  example: 0
                  type: integer
                pg_card_name:
                  description: |-
                    * Sender's cardholder name
                    Required if no pg_card_token
                  example: ''
                  type: string
                pg_card_recipient:
                  description: |-
                    * Recipient's card number
                    Required if no pg_card_recipient_token
                  example: 0
                  type: integer
                pg_card_recipient_token:
                  description: |-
                    * Recipient's saved card token
                    Required if no pg_card_recipient
                  example: ''
                  type: string
                pg_card_recipient_name:
                  description: '* Recipient''s cardholder name'
                  example: ''
                  type: string
                pg_save_sender_card:
                  description: '* Sign of the need to save the card for sending money'
                  example: ''
                  type: string
                pg_save_recipient_card:
                  description: '* Sign of the need to save the recipient''s card'
                  example: ''
                  type: string
                pg_sender_birthdate:
                  description: |-
                    Sender's date of birth, cannot be empty
                    Format: YYYY-MM-DD
                  example: ''
                  type: string
                pg_sender_country:
                  description: |-
                    Sender's country
                    Alpha-3 code, cannot be empty
                  example: ''
                  type: string
                pg_sender_city:
                  description: |-
                    Sender's city
                    Latin letters, maximum length 25 characters, cannot be empty
                  example: ''
                  type: string
                pg_sender_street:
                  description: |-
                    Sender's address (street)
                    Latin letters, maximum length 35 characters, cannot be empty
                  example: ''
                  type: string
                pg_sender_postal_code:
                  description: |-
                    Sender's postal code
                    Latin letters, maximum length 10 characters, cannot be empty
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_currency_from
                - pg_currency_to
                - pg_description
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_status>ok</pg_status>
                    <pg_payment_status>success</pg_payment_status>
                    <pg_3ds>1</pg_3ds>
                    <pg_3d_acsurl>https://bank-issuer-url.com/3ds-verify</pg_3d_acsurl>
                    <pg_order_id>ORD12345</pg_order_id>
                    <pg_payment_amount>1000.00</pg_payment_amount>
                    <pg_payout_amount>950.00</pg_payout_amount>
                    <pg_currency_from>KZT</pg_currency_from>
                    <pg_currency_to>USD</pg_currency_to>
                    <pg_card_token>abcd1234token</pg_card_token>
                    <pg_card_recipient_token>xyz9876token</pg_card_recipient_token>
                    <pg_card_mask>411111-XXXXXX-1111</pg_card_mask>
                    <pg_card_recipient_mask>422222-XXXXXX-2222</pg_card_recipient_mask>
                    <pg_payment_date>2024-09-02T12:19:01+00:00</pg_payment_date>
                    <pg_salt>YtfwCGiBHsFLpYGk</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    <pg_datetime>2024-09-02T12:19:01+00:00</pg_datetime>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Process:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>777777777</pg_payment_id>
                    <pg_order_id>980399</pg_order_id>
                    <pg_payment_amount>100</pg_payment_amount>
                    <pg_status>pending</pg_status>
                    <pg_currency_from>KZT</pg_currency_from>
                    <pg_payment_date/>
                    <pg_payment_status>process</pg_payment_status>
                    <pg_3ds>1</pg_3ds>
                    <pg_3d_acsurl>https://secure.freedompay.kz/v2/user/3ds-page/1234abcd-1234-5678-9aed-1234abcd</pg_3d_acsurl>
                    <pg_card_mask>4444-44XX-XXXX-4444</pg_card_mask>
                    <pg_datetime>2024-11-28T11:30:25+00:00</pg_datetime>
                    <pg_salt>WTfdgfdggsUu9E6qxLI</pg_salt>
                    <pg_sig>123b0b7af543ygdfhbfdjknf0f</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Process
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_error_code
                  - pg_error_description
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_order_id>980396</pg_order_id>
                    <pg_payment_amount>100</pg_payment_amount>
                    <pg_status>error</pg_status>
                    <pg_currency_from>KZT</pg_currency_from>
                    <pg_payment_date/>
                    <pg_payment_status>error</pg_payment_status>
                    <pg_3ds>0</pg_3ds>
                    <pg_card_mask>4444-44XX-XXXX-4444</pg_card_mask>
                    <pg_error_description>3DS код карты списания не введен или введен некорректно. Повторите попытку.</pg_error_description>
                    <pg_error_code>10004</pg_error_code>
                    <pg_datetime>2024-11-28T11:29:54+00:00</pg_datetime>
                    <pg_salt>AndfdshgKM0jTbYeI</pg_salt>
                    <pg_sig>e75da38a7247a645jnvfjb96e9ea87899</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Transfer
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9885527-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# 3DSecure

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/p2p/transfer_acs:
    post:
      summary: 3DSecure
      deprecated: false
      description: >-
        :::info[]

        - 3D Secure (3DS) is an authentication technology to protect against
        unauthorized use of cards. It allows for verifying the cardholder’s
        identity before the payment is processed

        - The authentication process works as follows: after entering the card
        details, the issuer’s website opens, prompting the cardholder to enter a
        password or secret code. The code is usually sent via SMS. If the code
        is entered correctly, the payment is authorized; if not, the transaction
        is declined

        - 3D Secure is available only for cards issued by banks that support
        this technology. Payments without 3D Secure are considered less secure

        :::


        #### Interaction diagram for 3ds transfer

        :::tip[]

        Status: *success/error/pending*

        :::


        ![G2G_API_V3-Making a transfer (P2P)  with
        3DS.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348621/image-preview)
      tags:
        - Gateway API/Sync API/Transfer
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            encoding:
              pg_sig:
                contentType: 'false'
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: ''
                  type: string
                pg_payment_id:
                  description: '* Transaction ID'
                  example: 0
                  type: integer
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_order_id>980484</pg_order_id>
                    <pg_payment_amount>10</pg_payment_amount>
                    <pg_status>ok</pg_status>
                    <pg_currency_from>USD</pg_currency_from>
                    <pg_payment_date>2024-11-28 16:42:24</pg_payment_date>
                    <pg_payment_status>success</pg_payment_status>
                    <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                    <pg_card_token>11zxzxzxzxz-7zxzxz-4zxzx-4444-djng364ce8</pg_card_token>
                    <pg_payout_amount>10</pg_payout_amount>
                    <pg_currency_to>USD</pg_currency_to>
                    <pg_card_recipient_mask>4444-44XX-XXXX-4444</pg_card_recipient_mask>
                    <pg_card_recipient_token>fafafafafa-eaea-413dg-ddsdf2-432juithnj</pg_card_recipient_token>
                    <pg_datetime>2024-11-28T11:42:34+00:00</pg_datetime>
                    <pg_salt>43JI35rmdgnR</pg_salt>
                    <pg_sig>gfdhgfedknj24kientl543njdxz</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_error_code
                  - pg_error_description
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>777777777</pg_payment_id>
                    <pg_order_id>980482</pg_order_id>
                    <pg_payment_amount>10</pg_payment_amount>
                    <pg_status>error</pg_status>
                    <pg_currency_from>USD</pg_currency_from>
                    <pg_payment_date/>
                    <pg_payment_status>error</pg_payment_status>
                    <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                    <pg_card_token>13fsdfg36-cgfd-4ds4-3333-fdgh23etr4</pg_card_token>
                    <pg_error_description>ERROR DESC</pg_error_description>
                    <pg_error_code>1000669</pg_error_code>
                    <pg_datetime>2024-11-28T11:42:11+00:00</pg_datetime>
                    <pg_salt>DwFdskPMJxPp</pg_salt>
                    <pg_sig>7a4ebb4e04dsgfdk34344a615414b98fa</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Transfer
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9886434-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# 3DSecure

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/p2p/transfer_acs:
    post:
      summary: 3DSecure
      deprecated: false
      description: >-
        :::info[]

        - 3D Secure (3DS) is an authentication technology to protect against
        unauthorized use of cards. It allows for verifying the cardholder’s
        identity before the payment is processed

        - The authentication process works as follows: after entering the card
        details, the issuer’s website opens, prompting the cardholder to enter a
        password or secret code. The code is usually sent via SMS. If the code
        is entered correctly, the payment is authorized; if not, the transaction
        is declined

        - 3D Secure is available only for cards issued by banks that support
        this technology. Payments without 3D Secure are considered less secure

        :::


        #### Interaction diagram for 3ds transfer

        :::tip[]

        Status: *success/error/pending*

        :::


        ![G2G_API_V3-Making a transfer (P2P)  with
        3DS.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348621/image-preview)
      tags:
        - Gateway API/Sync API/Transfer
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            encoding:
              pg_sig:
                contentType: 'false'
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: ''
                  type: string
                pg_payment_id:
                  description: '* Transaction ID'
                  example: 0
                  type: integer
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_order_id>980484</pg_order_id>
                    <pg_payment_amount>10</pg_payment_amount>
                    <pg_status>ok</pg_status>
                    <pg_currency_from>USD</pg_currency_from>
                    <pg_payment_date>2024-11-28 16:42:24</pg_payment_date>
                    <pg_payment_status>success</pg_payment_status>
                    <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                    <pg_card_token>11zxzxzxzxz-7zxzxz-4zxzx-4444-djng364ce8</pg_card_token>
                    <pg_payout_amount>10</pg_payout_amount>
                    <pg_currency_to>USD</pg_currency_to>
                    <pg_card_recipient_mask>4444-44XX-XXXX-4444</pg_card_recipient_mask>
                    <pg_card_recipient_token>fafafafafa-eaea-413dg-ddsdf2-432juithnj</pg_card_recipient_token>
                    <pg_datetime>2024-11-28T11:42:34+00:00</pg_datetime>
                    <pg_salt>43JI35rmdgnR</pg_salt>
                    <pg_sig>gfdhgfedknj24kientl543njdxz</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payout_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                    description: Saved card token
                  pg_card_recipient_token:
                    type: string
                    description: Saved recipient card token
                  pg_card_mask:
                    type: string
                    description: Saved card mask
                  pg_card_recipient_mask:
                    type: string
                    description: Recipient card mask
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_error_code
                  - pg_error_description
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_mask
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_card_mask
                  - pg_payment_amount
                  - pg_order_id
                  - pg_status
                  - pg_salt
                  - pg_payment_date
                  - pg_sig
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>777777777</pg_payment_id>
                    <pg_order_id>980482</pg_order_id>
                    <pg_payment_amount>10</pg_payment_amount>
                    <pg_status>error</pg_status>
                    <pg_currency_from>USD</pg_currency_from>
                    <pg_payment_date/>
                    <pg_payment_status>error</pg_payment_status>
                    <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                    <pg_card_token>13fsdfg36-cgfd-4ds4-3333-fdgh23etr4</pg_card_token>
                    <pg_error_description>ERROR DESC</pg_error_description>
                    <pg_error_code>1000669</pg_error_code>
                    <pg_datetime>2024-11-28T11:42:11+00:00</pg_datetime>
                    <pg_salt>DwFdskPMJxPp</pg_salt>
                    <pg_sig>7a4ebb4e04dsgfdk34344a615414b98fa</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
        x-200:Invalid Signature:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_salt
                  - pg_datetime
                  - pg_error_description
                  - pg_error_code
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>1100</pg_error_code>
                    <pg_error_description>Некорректная подпись запроса</pg_error_description>
                    <pg_datetime>2024-10-07T06:33:20+00:00</pg_datetime>
                    <pg_salt>7fkmeKvqQYackCJU</pg_salt>
                    <pg_sig>882e48ca30b5ad92001af82d96cecdab</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Invalid Signature
      security: []
      x-apidog-folder: Gateway API/Sync API/Transfer
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9886434-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Rates

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/p2p/rates:
    post:
      summary: Rates
      deprecated: false
      description: >-
        :::info[]

        This method is used to obtain information about the current rates at
        which currencies will be converted

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error/pending*

        :::


        ![image.png](https://api.apidog.com/api/v1/projects/640842/resources/348622/image-preview)
      tags:
        - Gateway API/Sync API/Transfer
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            encoding:
              pg_sig:
                contentType: 'false'
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_currency_from:
                  description: '* Charge currency'
                  example: ''
                  type: string
                pg_currency_to:
                  description: '* Transfer credit currency'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_status:
                    type: string
                  rates:
                    type: object
                    properties:
                      pg_currency_from:
                        type: string
                      pg_currency_to:
                        type: string
                      pg_rate:
                        type: number
                    x-apidog-orders:
                      - pg_currency_from
                      - pg_currency_to
                      - pg_rate
                    required:
                      - pg_currency_from
                      - pg_currency_to
                      - pg_rate
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - rates
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                required:
                  - pg_status
                  - rates
                  - pg_salt
                  - pg_sig
                  - pg_datetime
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>ok</pg_status>
                    <rate>
                        <pg_currency_from>KZT</pg_currency_from>
                        <pg_currency_to>EUR</pg_currency_to>
                        <pg_rate>0.85</pg_rate>
                    </rate>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>signature-def456</pg_sig>
                    <pg_datetime>2024-10-01T14:00:00+00:00</pg_datetime>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Transfer
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9886534-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Status

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/p2p/status:
    post:
      summary: Status
      deprecated: false
      description: >-
        :::info[]

        This method is used to get information about the current status of a
        transfer, such as whether it was successful, an error occurred, or is
        pending

        :::
      tags:
        - Gateway API/Sync API/Transfer
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            encoding:
              pg_sig:
                contentType: 'false'
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: ''
                  type: string
                pg_order_id:
                  type: integer
                  description: |-
                    * Payment ID in the merchant system
                    It is recommended to keep this field unique
                  example: 0
                pg_payment_id:
                  description: '* Transaction ID'
                  example: 0
                  type: integer
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                  pg_card_recipient_token:
                    type: string
                  pg_card_mask:
                    type: string
                  pg_card_recipient_mask:
                    type: string
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                  pg_payout_amount:
                    type: number
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_mask
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                required:
                  - pg_payment_id
                  - pg_card_recipient_mask
                  - pg_card_mask
                  - pg_card_recipient_token
                  - pg_card_token
                  - pg_currency_to
                  - pg_currency_from
                  - pg_payment_amount
                  - pg_order_id
                  - pg_payment_status
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_payment_date
                  - pg_datetime
                  - pg_payout_amount
              examples:
                '1':
                  summary: Success
                  value: |-
                    <?xml version="1.0" encoding="UTF-8"?>
                    <response>
                        <pg_payment_id>777777777</pg_payment_id>
                        <pg_order_id>980528</pg_order_id>
                        <pg_payment_amount>10</pg_payment_amount>
                        <pg_status>ok</pg_status>
                        <pg_payment_status>success</pg_payment_status>
                        <pg_currency_from>KZT</pg_currency_from>
                        <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                        <pg_payment_date>2024-11-28 16:46:51</pg_payment_date>
                        <pg_payout_amount>10</pg_payout_amount>
                        <pg_currency_to>KZT</pg_currency_to>
                        <pg_card_recipient_mask>4444-44XX-XXXX-4444</pg_card_recipient_mask>
                        <pg_card_recipient_token>c735446te-b354-43gw-35vf-9b8353fdga0a</pg_card_recipient_token>
                        <pg_datetime>2024-11-28T11:52:02+00:00</pg_datetime>
                        <pg_salt>JQlU3sl2TwJFGDTHgSZ0WnnCr0ZXfV</pg_salt>
                        <pg_sig>355048fgdfsgh4352145e983ee7</pg_sig>
                    </response>
                '2':
                  summary: Process
                  value: |-
                    <?xml version="1.0" encoding="UTF-8"?>
                    <response>
                        <pg_payment_id>777777777</pg_payment_id>
                        <pg_order_id>980565</pg_order_id>
                        <pg_payment_amount>10</pg_payment_amount>
                        <pg_status>ok</pg_status>
                        <pg_payment_status>process</pg_payment_status>
                        <pg_currency_from>USD</pg_currency_from>
                        <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                        <pg_payment_date></pg_payment_date>
                        <pg_datetime>2024-11-28T11:52:02+00:00</pg_datetime>
                        <pg_salt>qVRWzqAIxkFdfzGDdfcc52MbCZXFgBD</pg_salt>
                        <pg_sig>99437c1a93f3fgdgr4532vf879cc9a3ee</pg_sig>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Process:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_payment_status:
                    type: string
                  pg_order_id:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_currency_from:
                    type: string
                  pg_currency_to:
                    type: string
                  pg_card_token:
                    type: string
                  pg_card_recipient_token:
                    type: string
                  pg_card_mask:
                    type: string
                  pg_card_recipient_mask:
                    type: string
                  pg_payment_date:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                  pg_payout_amount:
                    type: number
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_payment_status
                  - pg_order_id
                  - pg_payment_amount
                  - pg_payout_amount
                  - pg_currency_from
                  - pg_currency_to
                  - pg_card_token
                  - pg_card_recipient_token
                  - pg_card_mask
                  - pg_card_recipient_mask
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                required:
                  - pg_payment_id
                  - pg_card_recipient_mask
                  - pg_card_mask
                  - pg_card_recipient_token
                  - pg_card_token
                  - pg_currency_to
                  - pg_currency_from
                  - pg_payment_amount
                  - pg_order_id
                  - pg_payment_status
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_payment_date
                  - pg_datetime
                  - pg_payout_amount
          headers: {}
          x-apidog-name: Process
        x-200:OK:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Status of request.
                  pg_error_code:
                    type: integer
                    description: 'Error code identifying the specific issue. '
                  pg_error_description:
                    type: string
                    description: Explanation of the error.
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
              example: "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<response>\r\n    <pg_status>error</pg_status>\r\n    <pg_error_code>11068</pg_error_code>\r\n    <pg_error_description>Payment not found.</pg_error_description>\r\n</response>"
          headers: {}
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Sync API/Transfer
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9886515-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Overview

### Work with cardstorage
:::note[]
- This is a method in which a client's bank card data (e.g., card number, expiration date, cardholder's name) is stored for future use. 
- This process is typically implemented for the user's convenience, so they don't have to re-enter their card details for each payment, as well as for conducting transactions using the card token.
:::



# Add

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/cardstorage/add:
    post:
      summary: Add
      deprecated: false
      description: >-
        :::info[]

        This method is used to add the card to cardstorage

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error/pending*

        :::


        ![G2G_API_V3-Adding a card with
        3ds.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348664/image-preview)
      tags:
        - Gateway API/Sync API/Card
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            encoding:
              pg_sig:
                contentType: 'false'
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: '* Merchant ID in {{project}}'
                  example: 0
                  type: integer
                pg_order_id:
                  description: '* Payment ID in the merchant system'
                  example: ''
                  type: string
                pg_description:
                  description: '* Payment description displayed to the buyer'
                  example: ''
                  type: string
                pg_user_id:
                  description: '* User ID in the merchant system'
                  example: 0
                  type: integer
                pg_card_pan:
                  description: '* Sender''s card number'
                  example: ''
                  type: string
                pg_card_token:
                  description: >-
                    * The card token for which you want to enrich the
                    data||string
                  example: ''
                  type: string
                pg_card_cvc:
                  description: '* CVC/CVV card password'
                  example: 0
                  type: integer
                pg_card_year:
                  description: '* Card expiration year'
                  example: 0
                  type: integer
                pg_card_month:
                  description: '* Card expiration month'
                  example: 0
                  type: integer
                pg_card_name:
                  description: '* Sender''s cardholder name'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_user_id
                - pg_card_cvc
                - pg_card_year
                - pg_card_month
                - pg_card_name
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: |-
            F - Frictionless Flow
            C - Challenge Flow
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_order_id:
                    type: string
                  pg_card_token:
                    type: string
                  pg_user_id:
                    type: string
                  pg_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_card_mask:
                    type: string
                  pg_secure_details:
                    type: integer
                    description: 3ds authentication mode when saving a card
                x-apidog-orders:
                  - pg_payment_id
                  - pg_order_id
                  - pg_status
                  - pg_card_mask
                  - pg_card_token
                  - pg_3d_acsurl
                  - pg_user_id
                  - pg_3ds
                  - pg_salt
                  - pg_sig
                  - pg_secure_details
                required:
                  - pg_payment_id
                  - pg_salt
                  - pg_3d_acsurl
                  - pg_3ds
                  - pg_status
                  - pg_user_id
                  - pg_order_id
                  - pg_sig
                  - pg_card_mask
                  - pg_secure_details
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>1610142012</pg_payment_id>
                    <pg_order_id>123453</pg_order_id>
                    <pg_status>ok</pg_status>
                    <pg_card_mask>4400-43XX-XXXX-1358</pg_card_mask>
                    <pg_3ds>0</pg_3ds>
                    <pg_secure_details>F</pg_secure_details>
                    <pg_card_token>2e387830-dc9d-4a2e-9e52-c50445e3c832</pg_card_token>
                    <pg_datetime>2025-08-20T06:36:25+00:00</pg_datetime>
                    <pg_salt>Ma9ez0PQCIjzbQ49</pg_salt>
                    <pg_sig>1d794787488f6b67d8118ae7cd094888</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: string
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                xml:
                  name: response
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>10000</pg_error_code>
                    <pg_error_description>Ошибка оплаты. Повторите попытку позже.</pg_error_description>
                    <pg_datetime>2024-10-11T14:29:29+00:00</pg_datetime>
                    <pg_salt>MOZpQbTR35FCVoOa</pg_salt>
                    <pg_sig>37046e2a7154654gfsfg3567088170b</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
      security: []
      x-apidog-folder: Gateway API/Sync API/Card
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9886819-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# 3DSecure

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/cardstorage/payment_acs:
    post:
      summary: 3DSecure
      deprecated: false
      description: >-
        :::info[]

        - When using this method, 3ds is required, therefore it is necessary to
        make a request to the ACS server of the card issuer bank

        - 3D Secure (3DS) is an authentication technology to protect against
        unauthorized use of cards. It allows for verifying the cardholder’s
        identity before the payment is processed

        - The authentication process works as follows: after entering the card
        details, the issuer’s website opens, prompting the cardholder to enter a
        password or secret code. The code is usually sent via SMS. If the code
        is entered correctly, the payment is authorized; if not, the transaction
        is declined

        - 3D Secure is available only for cards issued by banks that support
        this technology. Payments without 3D Secure are considered less secure

        :::
      tags:
        - Gateway API/Sync API/Card
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_payment_id:
                  description: '* Transaction ID'
                  example: 0
                  type: integer
                pg_md:
                  description: |-
                    * Parameter from the response
                    ACS server of the issuer.
                  example: ''
                  type: string
                pg_pares:
                  description: |-
                    * Parameter from response
                    ACS server of the issuer
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_md
                - pg_pares
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_order_id:
                    type: string
                  pg_card_token:
                    type: string
                  pg_user_id:
                    type: string
                  pg_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_card_mask:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_order_id
                  - pg_status
                  - pg_card_mask
                  - pg_card_token
                  - pg_3d_acsurl
                  - pg_user_id
                  - pg_3ds
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_salt
                  - pg_3d_acsurl
                  - pg_3ds
                  - pg_status
                  - pg_user_id
                  - pg_order_id
                  - pg_sig
                  - pg_card_mask
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_order_id>test</pg_order_id>
                    <pg_status>ok</pg_status>
                    <pg_card_mask>5555-55XX-XXXX-5555</pg_card_mask>
                    <pg_3ds>1</pg_3ds>
                    <pg_3d_acsurl>https://secure.freedompay.kz/v2/user/3ds-page/fxz32tcxc-24trf-dfg3-dfgdf-3543543543gdf</pg_3d_acsurl>
                    <pg_datetime>2024-09-11T15:57:53+00:00</pg_datetime>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>7fba2cf29fdh53462cb7cc91534635af</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: string
                  pg_error_description:
                    type: string
                  pg_datetime:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
                xml:
                  name: response
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_datetime
                  - pg_salt
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>10000</pg_error_code>
                    <pg_error_description>Ошибка оплаты. Повторите попытку позже.</pg_error_description>
                    <pg_datetime>2024-10-11T14:29:29+00:00</pg_datetime>
                    <pg_salt>MOZpQbTR35FCVoOa</pg_salt>
                    <pg_sig>37046e2a7154654gfsfg3567088170b</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
      security: []
      x-apidog-folder: Gateway API/Sync API/Card
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9888280-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# List

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/cardstorage/list:
    post:
      summary: List
      deprecated: false
      description: >-
        :::info[]

        This method is used to get a list of previously saved bank cards

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error*

        :::

        ![G2G_API_V3-Get card
        list.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348666/image-preview)
      tags:
        - Gateway API/Sync API/Card
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_user_id:
                  description: '* User ID in the merchant system'
                  example: 0
                  type: integer
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_user_id
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  card:
                    type: object
                    properties:
                      pg_status:
                        type: string
                      pg_card_token:
                        type: string
                      pg_is_filled:
                        type: boolean
                      pg_card_hash:
                        type: string
                      created_at:
                        type: string
                    x-apidog-orders:
                      - pg_status
                      - pg_card_token
                      - pg_is_filled
                      - pg_card_hash
                      - created_at
                    required:
                      - pg_status
                      - pg_card_token
                      - pg_is_filled
                      - pg_card_hash
                      - created_at
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - card
                  - pg_salt
                  - pg_sig
                required:
                  - card
                  - pg_salt
                  - pg_sig
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <card>
                        <pg_status>approved</pg_status>
                        <pg_card_token>abcd1234token</pg_card_token>
                        <pg_is_filled>1</pg_is_filled>
                        <pg_card_hash>411111-XXXXXX-1111</pg_card_hash>
                        <created_at>2024-09-02T12:19:01+00:00</created_at>
                    </card>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Card
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9888586-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Remove

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/cardstorage/remove:
    post:
      summary: Remove
      deprecated: false
      description: >-
        :::info[]

        This method is used to remove the card from the list of previously saved
        bank cards

        :::


        #### Interaction diagram

        :::tip[]

        Status: *success/error*

        :::

        ![G2G_API_V3-Deleting a
        card.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348667/image-preview)
      tags:
        - Gateway API/Sync API/Card
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_user_id:
                  description: '* User ID in the merchant''s system'
                  example: 0
                  type: integer
                pg_card_token:
                  description: '* Saved card token of the sender'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_user_id
                - pg_card_token
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_status:
                    type: string
                  deleted_at:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - deleted_at
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - deleted_at
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>success</pg_status>
                    <deleted_at>2024-09-02T12:19:01+00:00</deleted_at>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: string
                  pg_error_description:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_salt
                  - pg_sig
                xml:
                  name: response
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_salt
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>error</pg_status>
                    <pg_error_code>9999</pg_error_code>
                    <pg_error_description>Error desc</pg_error_description>
                    <pg_salt>MOZpQbTR35FCVoOa</pg_salt>
                    <pg_sig>37046e2a7154654gfsfg3567088170b</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Error
      security: []
      x-apidog-folder: Gateway API/Sync API/Card
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9888332-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Status

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/status_v2:
    post:
      summary: Status
      deprecated: false
      description: >-
        :::info[]

        This method is used to get information about the current status of a
        payment, such as whether it was successful, an error occurred, or is
        pending

        :::
      tags:
        - Gateway API/Sync API/Card
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_order_id:
                  description: '* Payment ID in the merchant system'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_order_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: number
                    description: Transaction ID
                  pg_order_id:
                    type: string
                    description: Order ID in the shop system
                    pattern: ^[a-zA-Z0-9]+$
                  pg_currency:
                    type: string
                    description: 'Payment currency. Example: KZT'
                  pg_status:
                    type: string
                    description: Request status. Latin characters only.
                  pg_payment_status:
                    type: string
                    description: Payment status. Latin characters only.
                  pg_amount:
                    type: number
                    description: Amount displayed in the payment
                  pg_clearing_amount:
                    type: number
                    description: Amount written off during payment clearing
                  pg_refund_amount:
                    type: number
                    description: Refunded amount
                  pg_user_email:
                    type: string
                    format: email
                    description: Payer's e-mail
                  pg_card_name:
                    type: string
                    description: Payer's name
                  pg_card_id:
                    type: number
                    description: >-
                      Card ID for paying with saved card (Deprecated). Example:
                      1234
                  pg_card_token:
                    type: string
                    description: >-
                      Card token for paying with saved card. Example:
                      ef741cfc-f85e-41a0-84e6-2ba964912182
                  pg_card_pan:
                    type: string
                    description: 'Masked card number. Example: 5483-18XX-XXXX-0293'
                  pg_card_exp:
                    type: string
                    description: 'Card Expiration Date. Example: 03/23'
                  pg_card_brand:
                    type: string
                    description: 'Card brand code. Example: VI'
                  pg_user_phone:
                    type: string
                    description: 'Payer''s phone number. Format: 77001234567'
                  pg_payment_date:
                    type: string
                    format: date-time
                    description: 'Payment date. Format: YYYY-MM-DD hh:mm:ss'
                  pg_captured:
                    type: number
                    description: >-
                      Flag indicating whether the write-off (clearing) of the
                      payment has passed. Values: 0 or 1
                  pg_refund_payments:
                    type: array
                    description: List of refunds for this payment
                    items:
                      type: object
                      properties:
                        pg_payment_id:
                          type: number
                          description: Transaction ID
                        pg_payment_status:
                          type: string
                          description: Payment status. Latin characters only.
                        pg_amount:
                          type: number
                          description: Amount set for refund
                        pg_payment_date:
                          type: string
                          format: date-time
                          description: >-
                            Payment date. Only successful returns have it.
                            Format: YYYY-MM-DD hh:mm:ss
                        pg_reference:
                          type: string
                          description: >-
                            Bank-Assigned Unique Bank Transaction Identifier
                            (RRN)
                        pg_failure_code:
                          type: number
                          description: >-
                            Return error code. Available only for returns with
                            the status 'error'.
                        pg_failure_description:
                          type: string
                          description: >-
                            Description of the return error. Only returns with
                            status 'error'.
                      x-apidog-orders:
                        - pg_payment_id
                        - pg_payment_status
                        - pg_amount
                        - pg_payment_date
                        - pg_reference
                        - pg_failure_code
                        - pg_failure_description
                  pg_revoked_payments:
                    type: array
                    description: List of revokes for this payment
                    items:
                      type: object
                      properties:
                        pg_payment_id:
                          type: number
                          description: Revoke transaction ID
                        pg_payment_status:
                          type: string
                          description: Revoke payment status. Latin characters only.
                      x-apidog-orders:
                        - pg_payment_id
                        - pg_payment_status
                  pg_reference:
                    type: string
                    description: >-
                      A unique bank transaction identifier assigned by the bank
                      (RRN)
                  pg_intreference:
                    type: string
                    description: >-
                      A unique bank transaction identifier assigned by the bank
                      (ARN)
                  pg_failure_code:
                    type: number
                    description: >-
                      Return error code. Only available for returns with 'error'
                      status.
                  pg_failure_description:
                    type: string
                    description: >-
                      Description of the return error. Available only for
                      returns with the status 'error'.
                  pg_auth_code:
                    type: string
                    description: Bank payment authorization code. Digits, length 6.
                  pg_salt:
                    type: string
                    description: Random string. Arbitrary numbers and Latin letters.
                  pg_sig:
                    type: string
                    description: Request digital signature. Numbers and Latin letters.
                  pg_datetime:
                    type: string
                    format: date-time
                    description: >-
                      Date and time of the request. Format:
                      YYYY-MM-DDThh:mm:ss±hh:mm.
                required:
                  - pg_payment_id
                  - pg_order_id
                  - pg_currency
                  - pg_status
                  - pg_amount
                  - pg_user_email
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                x-apidog-orders:
                  - pg_payment_id
                  - pg_order_id
                  - pg_currency
                  - pg_status
                  - pg_payment_status
                  - pg_amount
                  - pg_clearing_amount
                  - pg_refund_amount
                  - pg_user_email
                  - pg_card_name
                  - pg_card_id
                  - pg_card_token
                  - pg_card_pan
                  - pg_card_exp
                  - pg_card_brand
                  - pg_user_phone
                  - pg_payment_date
                  - pg_captured
                  - pg_refund_payments
                  - pg_revoked_payments
                  - pg_reference
                  - pg_intreference
                  - pg_failure_code
                  - pg_failure_description
                  - pg_auth_code
                  - pg_salt
                  - pg_sig
                  - pg_datetime
              examples:
                '1':
                  summary: Success
                  value: |-
                    <?xml version="1.0" encoding="UTF-8"?>
                    <response>
                      <pg_payment_id>1427057029</pg_payment_id>
                      <pg_order_id>2343253465454</pg_order_id>
                      <pg_currency>KZT</pg_currency>
                      <pg_status>ok</pg_status>
                      <pg_payment_status>success</pg_payment_status>
                      <pg_amount>1030</pg_amount>
                      <pg_clearing_amount>0</pg_clearing_amount>
                      <pg_refund_amount>0</pg_refund_amount>
                      <pg_user_email></pg_user_email>
                      <pg_card_name>NAME NAME</pg_card_name>
                      <pg_user_phone></pg_user_phone>
                      <pg_payment_date>2024-11-28 15:44:53</pg_payment_date>
                      <pg_card_pan>4400-44XX-XXXX-4444</pg_card_pan>
                      <pg_card_exp>12/24</pg_card_exp>
                      <pg_card_brand>string</pg_card_brand>
                      <pg_net_amount>1005.28</pg_net_amount>
                      <pg_reference>4333333333</pg_reference>
                      <pg_captured>0</pg_captured>
                      <pg_auth_code>932495</pg_auth_code>
                      <pg_intreference>TE5XTR4GGFF</pg_intreference>
                      <pg_salt>XeFNeRYiwcqlWPg9TZUj6pc9gj6KYBSb</pg_salt>
                      <pg_sig>d333fb3333b3f6e861c61682ba173c46</pg_sig>
                      <pg_datetime>2024-11-28T10:44:55+00:00</pg_datetime>
                    </response>
                '2':
                  summary: Error
                  value: |-
                    <?xml version="1.0" encoding="utf-8"?>
                    <response>
                        <pg_status>error</pg_status>
                        <pg_error_code>9999</pg_error_code>
                        <pg_error_description>ERROR_MESSAGE</pg_error_description>
                        <pg_salt>7ORw1FKsAkHleInh</pg_salt>
                        <pg_sig>c72f5aafe77304e882553cb9d73189d2</pg_sig>
                    </response>
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Error
        x-200:OK:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
              example: "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<response>\r\n    <pg_status>error</pg_status>\r\n    <pg_error_code>11068</pg_error_code>\r\n    <pg_error_description>Payment not found.</pg_error_description>\r\n</response>"
          headers: {}
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Sync API/Card
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-13528554-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Overview

### Token Pay
:::info[]
Card token payment is used to make a payment where a token is used instead of real card details (e.g., the card number). 
A token is a unique identifier generated for a specific card and used for transactions, ensuring data security.
When using this method, it is necessary to pass the `pg_card_token` in the request to the Freedom Pay Gateway.
This method may only be available if the card has been previously saved and tokenized.
To use this method, you should contact your manager.
:::

---
### Apple / Google
:::info[]
A fast and secure way for one-touch online purchases. A customer of the store can pay with any card saved in his account. For merchant this payment will be processed like a regular payment by card.

If the purchase is made from a mobile device supporting Apple/Google/Samsung Pay, the customer will be asked to confirm the payment using a password, fingerprint or face recognition.

If the purchase is made from a device without the Apple/Google/Samsung Pay app, the customer can select any saved card in his account and confirm payment by passing 3D Secure authentication.

Additionally in the request to Freedom Pay Gateway it is necessary to pass parameters `pg_eci_indicator`, `pg_online_payment_cryptogram`, `pg_payment_method`(google_pay or apple_pay)
:::

#### Interaction diagram for Token Pay and Apple / Google
:::tip[]
Status: *success/error/pending*
:::

![G2G_API_V3-Making a payment wiith Samsung Pay.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348623/image-preview)

---
### Token Payout
:::info[]
Card token payout is used to make a payout where a token is used instead of real card details (e.g., the card number). 

A token is a unique identifier generated for a specific card and used for transactions, ensuring data security.

When using this method, it is necessary to pass the `pg_card_token` in the request to the Freedom Pay Gateway.
To use this method, you should contact your manager.
:::

#### Interaction diagram
:::tip[]
Status: *success/error/pending*
:::

![G2G_API_V3-Payout to card token.drawio.png](https://api.apidog.com/api/v1/projects/640842/resources/348660/image-preview)

---
### Status
:::info[]
This method is used to get information about the current status of a payment, such as whether it was successful, an error occurred, or is pending etc.
:::

# Token Pay

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/payment:
    post:
      summary: Token Pay
      deprecated: false
      description: ''
      tags:
        - Gateway API/Sync API/Token
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: number
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                     It is recommended to keep this field unique
                  example: ''
                  type: string
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_currency:
                  type: integer
                  description: '* Currency in which the amount is specified'
                  example: ''
                pg_description:
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                  type: string
                pg_language:
                  type: boolean
                  description: '* Error text language'
                  example: ''
                pg_user_id:
                  type: number
                  description: >-
                    * User ID in the merchant's system

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                pg_card_token:
                  description: '* Saved card token of the sender'
                  example: ''
                  type: string
                pg_param1:
                  type: integer
                  description: '* Additional parameter 1'
                  example: ''
                pg_param2:
                  type: boolean
                  description: '* Additional parameter 2'
                  example: ''
                pg_param3:
                  description: '* Additional parameter 3'
                  example: ''
                  type: string
                pg_salt:
                  type: integer
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                pg_sig:
                  type: integer
                  description: '* Request signature'
                  example: ''
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_user_id
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: Payment ID
                  pg_status:
                    type: string
                    description: ok
                  pg_merchant_id:
                    type: integer
                  pg_order_id:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_merchant_id
                  - pg_order_id
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_merchant_id
                  - pg_sig
                  - pg_salt
                  - pg_order_id
                  - pg_datetime
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_status>ok</pg_status>
                    <pg_payment_id>7777777777</pg_payment_id>
                    <pg_merchant_id>9970</pg_merchant_id>
                    <pg_order_id>ORD12345</pg_order_id>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>ccee466c01c2332d8a065d6108fd686b</pg_sig>
                    <pg_datetime>2024-09-02T12:19:01+00:00</pg_datetime>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Token
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9888724-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Apple Pay

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/payment:
    post:
      summary: Apple Pay
      deprecated: false
      description: ''
      tags:
        - Gateway API/Sync API/Token
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: number
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                     It is recommended to keep this field unique
                  example: ''
                  type: string
                pg_amount:
                  type: number
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_currency:
                  description: '* Currency in which the amount is specified'
                  example: ''
                  type: string
                pg_description:
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                  type: string
                pg_auto_clearing:
                  type: boolean
                  description: >-
                    * Clearing type (0 or 1)

                    1 - automatic write-off after successful authorization, 0 -
                    write-off by launching the clearing method
                  example: ''
                pg_payment_method:
                  type: string
                  examples:
                    - apple_pay
                  description: '* Payment by tokenized method'
                  example: ''
                pg_card_pan:
                  type: string
                  examples:
                    - 4111XXXXXXXX1111
                  description: '* Virtual pan token from apple'
                  example: ''
                pg_card_year:
                  type: integer
                  examples:
                    - 31
                  description: '* Virtual pan tokens expiration year, from apple'
                  example: 0
                pg_card_month:
                  type: integer
                  examples:
                    - 12
                  description: '* Virtual pan tokens expiration month, from apple'
                  example: 0
                pg_card_name:
                  description: '* Name and surname of card holders'
                  example: ''
                  type: string
                pg_online_payment_cryptogram:
                  type: string
                  examples:
                    - APlNRdHvE+geASgppg/dAoABFAA=
                  description: '* TAVV cryptogram from apple'
                  example: ''
                "pg_eci_indicator\t":
                  type: string
                  examples:
                    - '00'
                    - '01'
                    - '02'
                    - '05'
                    - '06'
                    - '07'
                  description: >-
                    * Electronic Commerce Indicator (ECI) is a value returned by
                    Directory Servers (namely Visa, MasterCard) indicating the
                    outcome of authentication attempted on transactions enforced
                    by 3DS
                  example: ''
                pg_param1:
                  description: '* Additional parameter 1'
                  example: ''
                  type: string
                pg_param2:
                  description: '* Additional parameter 2'
                  example: ''
                  type: string
                pg_param3:
                  description: '* Additional parameter 3'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_payment_method
                - pg_card_pan
                - pg_card_year
                - pg_card_month
                - pg_card_name
                - pg_online_payment_cryptogram
                - "pg_eci_indicator\t"
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: Payment ID
                  pg_status:
                    type: string
                    description: ok
                  pg_3ds:
                    type: boolean
                  pg_3d_acsurl:
                    type: string
                  pg_3d_md:
                    type: string
                  pg_3d_pareq:
                    type: string
                  pg_recurring_profile:
                    type: integer
                  pg_card_id:
                    type: string
                  pg_card_token:
                    type: string
                  pg_auth_code:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                  pg_datetime:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_3d_md
                  - pg_3d_pareq
                  - pg_recurring_profile
                  - pg_card_id
                  - pg_card_token
                  - pg_auth_code
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_3d_acsurl
                  - pg_sig
                  - pg_salt
                  - pg_auth_code
                  - pg_card_token
                  - pg_card_id
                  - pg_recurring_profile
                  - pg_3d_pareq
                  - pg_3d_md
                  - pg_datetime
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>1234567890</pg_payment_id>
                    <pg_status>ok</pg_status>
                    <pg_3ds>1</pg_3ds>
                    <pg_3d_acsurl>https://bank.com/3ds-validation</pg_3d_acsurl>
                    <pg_3d_md>abc123456</pg_3d_md>
                    <pg_3d_pareq>xyz-98765</pg_3d_pareq>
                    <pg_recurring_profile>12345</pg_recurring_profile>
                    <pg_card_id>9876543210</pg_card_id>
                    <pg_card_token>token-abc123</pg_card_token>
                    <pg_auth_code>123456</pg_auth_code>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>signature-abc123</pg_sig>
                    <pg_datetime>2024-09-02T12:19:01+00:00</pg_datetime>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Token
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9856298-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Google Pay

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/payment:
    post:
      summary: Google Pay
      deprecated: false
      description: ''
      tags:
        - Gateway API/Sync API/Token
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_order_id:
                  description: |-
                    * Payment ID in the merchant system
                     It is recommended to keep this field unique
                  example: ''
                  type: string
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount in pg_currency'
                  example: 0
                pg_currency:
                  description: '* Currency in which the amount is specified'
                  example: ''
                  type: string
                pg_description:
                  type: number
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                pg_auto_clearing:
                  description: >-
                    * Clearing type (0 or 1)

                    1 - automatic write-off after successful authorization, 0 -
                    write-off by launching the clearing method
                  example: ''
                  type: string
                pg_payment_method:
                  type: string
                  examples:
                    - google_pay
                  description: '* Payment by tokenized method'
                  example: google_pay
                pg_user_ip:
                  type: integer
                  description: '* Client''s IP address'
                  example: ''
                pg_online_payment_cryptogram:
                  type: string
                  description: '* TAVV cryptogram from google'
                  example: APlNRdHvE+geASgppg/dAoABFAA=
                "pg_eci_indicator\t":
                  type: string
                  examples:
                    - '00'
                    - '01'
                    - '02'
                    - '05'
                    - '06'
                    - '07'
                  description: >-
                    * Electronic Commerce Indicator (ECI) is a value returned by
                    Directory Servers (namely Visa, MasterCard) indicating the
                    outcome of authentication attempted on transactions enforced
                    by 3DS
                  example: ''
                pg_salt:
                  type: integer
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                pg_sig:
                  type: integer
                  description: '* Request signature'
                  example: ''
                pg_card_pan:
                  description: '* Virtual pan token from google'
                  example: 4111XXXXXXXX1111
                  type: string
                pg_card_year:
                  description: '* Virtual pan tokens expiration year, from google'
                  example: '31'
                  type: string
                pg_card_month:
                  description: '* Virtual pan tokens expiration month, from google'
                  example: '06'
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_payment_method
                - pg_online_payment_cryptogram
                - "pg_eci_indicator\t"
                - pg_salt
                - pg_sig
                - pg_card_pan
                - pg_card_year
                - pg_card_month
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                    description: Payment ID
                  pg_status:
                    type: string
                    description: ok
                  pg_3ds:
                    type: boolean
                  pg_auth_code:
                    type: string
                  pg_reference:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_auth_code
                  - pg_reference
                  - pg_salt
                  - pg_sig
                xml: {}
                required:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_sig
                  - pg_salt
                  - pg_reference
                  - pg_auth_code
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>685462745</pg_payment_id>
                    <pg_status>ok</pg_status>
                    <pg_3ds>0</pg_3ds>
                    <pg_auth_code>116658</pg_auth_code>
                    <pg_reference>482481615785</pg_reference>
                    <pg_salt>ntb4oJhg46xnJqlU</pg_salt>
                    <pg_sig>7828753fe55bea789974fcd233197669</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success without 3DS
        x-200:Success with 3DS:
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_3ds:
                    type: boolean
                  pg_3d_md:
                    type: string
                  pg_3d_acsurl:
                    type: string
                  pg_3d_pareq:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_status
                  - pg_3ds
                  - pg_3d_md
                  - pg_3d_acsurl
                  - pg_3d_pareq
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_3d_acsurl
                  - pg_3d_md
                  - pg_3ds
                  - pg_status
                  - pg_3d_pareq
                  - pg_salt
                  - pg_sig
              example: |-
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>685462745</pg_payment_id>
                    <pg_status>ok</pg_status>
                    <pg_3ds>1</pg_3ds>
                    <pg_3d_md>YTE5OThjNTEtOGNjZi00MDQ1LWE3M2ItZTcxMjI0NjkzMTVl</pg_3d_md>
                    <pg_3d_acsurl>https://secure.freedompay.kz/v1/v2_3ds_way4/user/3ds-page/561a9397-81ed-480a-a777-21b38dc02de9</pg_3d_acsurl>
                    <pg_3d_pareq>eyJtZXNzYWdlVHlwZSI6IkNSZXEiLCJtZXNzYWdlVmVyc2lvbiI6IjIuMS4wIiwidGhyZWVEU1NlcnZlclRyYW5zSUQiOiJhMTk5OGM1MS04Y2NmLTQwNDUtYTczYi1lNzEyMjQ2OTMxNWUiLCJhY3NUcmFuc0lEIjoiZDk1OTM3NGYtZDE0Yi00MjEzLTkwMmItN2Q1YmYwOWFkYTdlIiwiY2hhbGxlbmdlV2luZG93U2l6ZSI6IjA1In0</pg_3d_pareq>
                    <pg_salt>GGADkDBS8eLFtQtL</pg_salt>
                    <pg_sig>7b1da0a4639625f2686bd7084d09a641</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success with 3DS
      security: []
      x-apidog-folder: Gateway API/Sync API/Token
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9890798-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Token Payout

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/reg2reg:
    post:
      summary: Token Payout
      deprecated: false
      description: ''
      tags:
        - Gateway API/Sync API/Token
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                  type: integer
                pg_order_id:
                  type: number
                  description: |-
                    * Payment ID in the merchant system
                     It is recommended to keep this field unique
                  example: ''
                pg_amount:
                  type: number
                  minimum: 0.01
                  description: '* Payment amount'
                  example: 0
                pg_description:
                  description: >-
                    * Payment description

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: ''
                  type: string
                pg_order_time_limit:
                  description: '* Time limit for making a payment'
                  example: ''
                  type: string
                pg_user_id:
                  type: integer
                  description: >-
                    * User ID in the merchant's system

                    (These parameters may include parameters from other
                    sections. For the effective operation of SecureBox, it is
                    recommended to follow the validation guidelines and field
                    examples from this section)
                  example: 0
                pg_post_link:
                  description: '* URL to which payment status response is sent'
                  example: ''
                  type: string
                pg_card_token_to:
                  description: >-
                    * Token of the card to transfer money to (returned when
                    registering the card)
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * A random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_order_id
                - pg_amount
                - pg_description
                - pg_order_time_limit
                - pg_user_id
                - pg_post_link
                - pg_salt
                - pg_sig
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: integer
                  pg_merchant_id:
                    type: integer
                  pg_status:
                    type: string
                  pg_order_id:
                    type: string
                  pg_balance:
                    type: number
                  pg_card_hash:
                    type: string
                  pg_card_token:
                    type: string
                  pg_payment_amount:
                    type: number
                  pg_payment_date:
                    type: string
                  pg_error_code:
                    type: number
                  pg_error_description:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_payment_id
                  - pg_merchant_id
                  - pg_status
                  - pg_order_id
                  - pg_balance
                  - pg_card_hash
                  - pg_card_token
                  - pg_payment_amount
                  - pg_payment_date
                  - pg_error_code
                  - pg_error_description
                  - pg_salt
                  - pg_sig
                required:
                  - pg_payment_id
                  - pg_error_description
                  - pg_error_code
                  - pg_payment_date
                  - pg_payment_amount
                  - pg_card_token
                  - pg_card_hash
                  - pg_balance
                  - pg_order_id
                  - pg_status
                  - pg_merchant_id
                  - pg_salt
                  - pg_sig
              example: |
                <?xml version="1.0" encoding="utf-8"?>
                <response>
                    <pg_payment_id>1234567890</pg_payment_id>
                    <pg_merchant_id>9970</pg_merchant_id>
                    <pg_status>ok</pg_status>
                    <pg_order_id>ABC12345</pg_order_id>
                    <pg_balance>5000.75</pg_balance>
                    <pg_card_hash>39b32dfc9ed18533ee98b921687ad87a</pg_card_hash>
                    <pg_card_token>token-xyz987</pg_card_token>
                    <pg_payment_amount>100.00</pg_payment_amount>
                    <pg_payment_date>2024-09-02T12:19:01+00:00</pg_payment_date>
                    <pg_error_code>0</pg_error_code>
                    <pg_error_description>Description</pg_error_description>
                    <pg_salt>some random string</pg_salt>
                    <pg_sig>signature-abc123</pg_sig>
                </response>
          headers: {}
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Sync API/Token
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9881026-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Status

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /g2g/status_v2:
    post:
      summary: Status
      deprecated: false
      description: ''
      tags:
        - Gateway API/Sync API/Token
      parameters: []
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                pg_merchant_id:
                  type: integer
                  description: |-
                    * Merchant ID in {{project}}
                    Issued upon connection
                  example: 0
                pg_payment_id:
                  type: integer
                  description: '* Transaction ID'
                  example: 0
                pg_order_id:
                  description: '* Payment ID in the merchant system'
                  example: ''
                  type: string
                pg_salt:
                  description: >-
                    * Random string consisting of arbitrary numbers and Latin
                    letters
                  example: ''
                  type: string
                pg_sig:
                  description: '* Request signature'
                  example: ''
                  type: string
              required:
                - pg_merchant_id
                - pg_payment_id
                - pg_order_id
                - pg_salt
                - pg_sig
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/xml:
              schema:
                type: object
                properties:
                  pg_payment_id:
                    type: number
                    description: Transaction ID
                  pg_order_id:
                    type: string
                    description: Order ID in the shop system
                    pattern: ^[a-zA-Z0-9]+$
                  pg_currency:
                    type: string
                    description: 'Payment currency. Example: KZT'
                  pg_status:
                    type: string
                    description: Request status. Latin characters only.
                  pg_payment_status:
                    type: string
                    description: Payment status. Latin characters only.
                  pg_amount:
                    type: number
                    description: Amount displayed in the payment
                  pg_clearing_amount:
                    type: number
                    description: Amount written off during payment clearing
                  pg_refund_amount:
                    type: number
                    description: Refunded amount
                  pg_user_email:
                    type: string
                    format: email
                    description: Payer's e-mail
                  pg_card_name:
                    type: string
                    description: Payer's name
                  pg_card_id:
                    type: number
                    description: >-
                      Card ID for paying with saved card (Deprecated). Example:
                      1234
                  pg_card_token:
                    type: string
                    description: >-
                      Card token for paying with saved card. Example:
                      ef741cfc-f85e-41a0-84e6-2ba964912182
                  pg_card_pan:
                    type: string
                    description: 'Masked card number. Example: 5483-18XX-XXXX-0293'
                  pg_card_exp:
                    type: string
                    description: 'Card Expiration Date. Example: 03/23'
                  pg_card_brand:
                    type: string
                    description: 'Card brand code. Example: VI'
                  pg_user_phone:
                    type: string
                    description: 'Payer''s phone number. Format: 77001234567'
                  pg_payment_date:
                    type: string
                    format: date-time
                    description: 'Payment date. Format: YYYY-MM-DD hh:mm:ss'
                  pg_captured:
                    type: number
                    description: >-
                      Flag indicating whether the write-off (clearing) of the
                      payment has passed. Values: 0 or 1
                  pg_refund_payments:
                    type: array
                    description: List of refunds for this payment
                    items:
                      type: object
                      properties:
                        pg_payment_id:
                          type: number
                          description: Transaction ID
                        pg_payment_status:
                          type: string
                          description: Payment status. Latin characters only.
                        pg_amount:
                          type: number
                          description: Amount set for refund
                        pg_payment_date:
                          type: string
                          format: date-time
                          description: >-
                            Payment date. Only successful returns have it.
                            Format: YYYY-MM-DD hh:mm:ss
                        pg_reference:
                          type: string
                          description: >-
                            Bank-Assigned Unique Bank Transaction Identifier
                            (RRN)
                        pg_failure_code:
                          type: number
                          description: >-
                            Return error code. Available only for returns with
                            the status 'error'.
                        pg_failure_description:
                          type: string
                          description: >-
                            Description of the return error. Only returns with
                            status 'error'.
                      x-apidog-orders:
                        - pg_payment_id
                        - pg_payment_status
                        - pg_amount
                        - pg_payment_date
                        - pg_reference
                        - pg_failure_code
                        - pg_failure_description
                  pg_revoked_payments:
                    type: array
                    description: List of revokes for this payment
                    items:
                      type: object
                      properties:
                        pg_payment_id:
                          type: number
                          description: Revoke transaction ID
                        pg_payment_status:
                          type: string
                          description: Revoke payment status. Latin characters only.
                      x-apidog-orders:
                        - pg_payment_id
                        - pg_payment_status
                  pg_reference:
                    type: string
                    description: >-
                      A unique bank transaction identifier assigned by the bank
                      (RRN)
                  pg_intreference:
                    type: string
                    description: >-
                      A unique bank transaction identifier assigned by the bank
                      (ARN)
                  pg_failure_code:
                    type: number
                    description: >-
                      Return error code. Only available for returns with 'error'
                      status.
                  pg_failure_description:
                    type: string
                    description: >-
                      Description of the return error. Available only for
                      returns with the status 'error'.
                  pg_auth_code:
                    type: string
                    description: Bank payment authorization code. Digits, length 6.
                  pg_salt:
                    type: string
                    description: Random string. Arbitrary numbers and Latin letters.
                  pg_sig:
                    type: string
                    description: Request digital signature. Numbers and Latin letters.
                  pg_datetime:
                    type: string
                    format: date-time
                    description: >-
                      Date and time of the request. Format:
                      YYYY-MM-DDThh:mm:ss±hh:mm.
                required:
                  - pg_payment_id
                  - pg_order_id
                  - pg_currency
                  - pg_status
                  - pg_amount
                  - pg_user_email
                  - pg_payment_date
                  - pg_salt
                  - pg_sig
                  - pg_datetime
                x-apidog-orders:
                  - pg_payment_id
                  - pg_order_id
                  - pg_currency
                  - pg_status
                  - pg_payment_status
                  - pg_amount
                  - pg_clearing_amount
                  - pg_refund_amount
                  - pg_user_email
                  - pg_card_name
                  - pg_card_id
                  - pg_card_token
                  - pg_card_pan
                  - pg_card_exp
                  - pg_card_brand
                  - pg_user_phone
                  - pg_payment_date
                  - pg_captured
                  - pg_refund_payments
                  - pg_revoked_payments
                  - pg_reference
                  - pg_intreference
                  - pg_failure_code
                  - pg_failure_description
                  - pg_auth_code
                  - pg_salt
                  - pg_sig
                  - pg_datetime
          headers: {}
          x-apidog-name: Success
        x-200:Error:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                  pg_error_code:
                    type: integer
                  pg_error_description:
                    type: string
                  pg_salt:
                    type: string
                  pg_sig:
                    type: string
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                  - pg_salt
                  - pg_sig
                required:
                  - pg_status
                  - pg_sig
                  - pg_salt
                  - pg_error_description
                  - pg_error_code
          headers: {}
          x-apidog-name: Error
        x-200:OK:
          description: ''
          content:
            application/xml:
              schema:
                title: ''
                type: object
                properties:
                  pg_status:
                    type: string
                    description: Status of request.
                  pg_error_code:
                    type: integer
                    description: 'Error code identifying the specific issue. '
                  pg_error_description:
                    type: string
                    description: Explanation of the error.
                x-apidog-orders:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
                required:
                  - pg_status
                  - pg_error_code
                  - pg_error_description
              example: "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<response>\r\n    <pg_status>error</pg_status>\r\n    <pg_error_code>11068</pg_error_code>\r\n    <pg_error_description>Payment not found.</pg_error_description>\r\n</response>"
          headers: {}
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Sync API/Token
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-13528434-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# Overview

### Introduction
:::note[]
- **Request Type:** POST  
- **Request Format:** application/json 
:::
 
---
### Request Headers
:::note[]
- **X-Action** - The method being called.
- **X-Request-Id** - Unique request ID (UUID).
- **Accept-Language** - Response language of the system (currently not used).
- **X-JWS-Signature** - Request signature (detailed explanation below).
- **Content-Type** - Must be `application/json`.
- **Accept** - Must be `application/json`.
:::

---
### Response Headers
:::note[]
- **X-Action** - The method.
- **X-Request-Id** - Unique request ID (UUID).
- **X-Datetime** - Date and time of request processing.
- **X-Request-Status** - Request processing status.
:::

---
### The API has three main URLs
:::note[]
- `{domain}/v5/g2g/create` - Creates an object in the PG system.
- `{domain}/v5/g2g/read` - Retrieves information about an object.
- `{domain}/v5/g2g/edit` - Updates information about an object.
:::

&emsp;An object in the payment system represents an entity or resource that the system interacts with to process payments and manage financial operations. This object can be a payment, card, account, etc. 
&emsp;The object contains a set of attributes that define its properties, status, and transaction history. Interaction with the object is performed through the payment system's API, allowing various operations such as creation, retrieval, updating, and deletion of objects, as well as executing additional actions within the context of a specific object.

---
### Generating the X-JWS-Signature
&emsp;To send any request, a request signature must be generated using JWS technology.  

&emsp;The JWS format must include the mandatory blocks **header** and **signature** and should be passed in the request header **X-JWS-Signature**.  

---
### Header Structure (all fields are required)
```json 
{
    "uri": "/v5/g2g/create",
    "auth_id": "123456",
    "method": "POST",
    "params": "",
    "alg": "HS256"
}
```

---
### Header Structure description
| Field    | Description                                      |
|----------|--------------------------------------------------|
| uri      | The path to the API endpoint being called        |
| auth_id  | User ID for signature verification               |
| method   | Request method                                   |
| params   | Reserved field                                   |
| alg      | Encryption algorithm                             |

---
### Payload Structure
&emsp;The payload for generating JWS includes the HTTP request body.  
&emsp;The supported signature encryption algorithm is **HS256**, and the **merchant's secret_key** should be used as the signing key.  
**Example of Signature Generation:**
**Header**
```json
{
    "uri": "/v5/g2g/create",
    "auth_id": "123456",
    "method": "POST",
    "params": "",
    "alg": "HS256"
}
```

**Payload:**
```json
{
  "amount": 123.42,
  "currency": "KZT",
  "description": "description",
  "order_id": "order_id",
  "user_id": "user_id",
  "auto_clearing": true,
  "from": {
    "type": "card",
    "card": {
      "name": "CARD HOLDER",
      "pan": "4400444400004440",
      "cvc": "123",
      "year": 30,
      "month": 12
    },
    "save": true,
    "recurrent": {
      "lifetime": 3
    }
  },
  "device": {
    "user_ip": "123.123.123.123"
  },
  "urls": {
    "check_url": "https://webhook.site/2af177da-0d72-4651-a31e-a0ea56ccc8a4",
    "result_url": "https://webhook.site/2af177da-0d72-4651-a31e-a0ea56ccc8a4"
  }
}
```

**Encryption Key:** `123456`  
**Generated JWS:**  
```
eyJ1cmkiOiIvdjUvZzJnL2NyZWF0ZSIsImF1dGhfaWQiOiIxMjM0NTYiLCJtZXRob2QiOiJQT1NUIiwicGFyYW1zIjoiIiwiYWxnIjoiSFMyNTYifQ..82NnkgrNjfYu2UnAajnVsJUn2AgJWsqnmCK4x5A7zt0
```

# create payment

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/create:
    post:
      summary: create payment
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/create
      parameters:
        - name: Accept
          in: header
          description: >-
            Indicates the media types that the client is able to understand from
            the server response.
          required: true
          example: ''
          schema:
            type: string
            default: application/json
        - name: Content-Type
          in: header
          description: Specifies the media type of the resource being sent to the server.
          required: true
          example: ''
          schema:
            type: string
            default: application/json
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: ''
          schema:
            type: string
            examples:
              - >-
                eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
        - name: X-Action
          in: header
          description: Invoked method.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.payment.create
        - name: X-Request-Id
          in: header
          description: >-
            Unique request ID (UUID).

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: ''
          schema:
            type: string
            examples:
              - 01978c2b-f191-7b56-92f8-20c7c401d1fc
      requestBody:
        content:
          application/xml:
            schema:
              type: object
              properties:
                amount:
                  type: number
                  description: Payment amount.
                  format: float
                currency:
                  type: string
                  examples:
                    - KZT
                  description: Payment currency.
                description:
                  type: string
                  examples:
                    - description
                  description: Payment description.
                order_id:
                  type: string
                  examples:
                    - '1234'
                  description: >-
                    Order number in the merchant's system.

                    If the same order_id is sent more than once, the API
                    guarantees idempotent behavior and returns the original
                    response.
                user_id:
                  type: string
                  examples:
                    - '12345'
                  description: >-
                    Unique user identifier on the merchant side. Must match the
                    owner of the saved card.
                auto_clearing:
                  type: boolean
                  default: true
                  description: Flag indicating the need for automatic clearing.
                from:
                  type: object
                  properties:
                    type:
                      type: string
                      description: Type of the debit object.
                      examples:
                        - card
                        - tokenized
                        - recurrent
                        - saved
                    card:
                      type: object
                      properties:
                        name:
                          type: string
                          examples:
                            - Test Testov
                          description: Cardholder's name.
                        pan:
                          type: string
                          examples:
                            - '4400444400004440'
                          description: Card PAN (Primary Account Number).
                        cvc:
                          type: string
                          examples:
                            - '123'
                          description: Card CVC code.
                        year:
                          type: integer
                          examples:
                            - 30
                          description: Card expiration year.
                        month:
                          type: integer
                          examples:
                            - 5
                          description: Card expiration month.
                        uuid:
                          type: string
                          title: required if type = saved
                          examples:
                            - 01978c91-569a-7471-ae7b-942e7f045fac
                          description: Card token.
                        token:
                          type: string
                          description: >-
                            Unique identifier of the previously saved card in
                            our Freedom Pay Card-on-File storage.
                          examples:
                            - d6a069dc-0fac-40d4-be4f-2273350ee256
                      x-apidog-orders:
                        - name
                        - pan
                        - cvc
                        - year
                        - month
                        - uuid
                        - token
                      description: >-
                        Object containing card data. (required if from.type =
                        "card" or "tokenized")
                      title: required if type=card or saved
                      required:
                        - name
                        - pan
                        - year
                        - month
                    recurrent:
                      type: object
                      properties:
                        lifetime:
                          type: integer
                          minimum: 1
                          maximum: 156
                          examples:
                            - 5
                          description: Lifetime of recurrent profile in months.
                      x-apidog-orders:
                        - lifetime
                      description: >-
                        Contains info about starting a recurrent profile or
                        performing a recurrent payment.
                      required:
                        - lifetime
                      title: required if type = recurrent
                    token:
                      type: object
                      properties:
                        type:
                          type: string
                          description: 'Type of token used in the payment creation request. '
                          examples:
                            - applepay
                            - googlepay
                            - vts
                            - mscof
                      x-apidog-orders:
                        - type
                      description: >-
                        Object for tokenized payments. (required if from.type =
                        "tokenized")
                      required:
                        - type
                    save:
                      type: boolean
                      description: >-
                        Flag indicating whether the card should be saved in the
                        Freedom Pay Card-on-File storage for future payments.
                      default: false
                  required:
                    - type
                  x-apidog-orders:
                    - type
                    - card
                    - recurrent
                    - token
                    - save
                device:
                  type: object
                  properties:
                    user_ip:
                      type: string
                      examples:
                        - 84.252.158.239
                      description: Client’s IP address.
                  x-apidog-orders:
                    - user_ip
                  description: Payer’s device information.
              required:
                - currency
                - description
                - order_id
                - auto_clearing
                - from
                - amount
              x-apidog-orders:
                - amount
                - currency
                - description
                - order_id
                - user_id
                - auto_clearing
                - from
                - device
            examples:
              '1':
                value:
                  amount: 10
                  currency: KZT
                  description: desc
                  order_id: 123test
                  auto_clearing: false
                  from:
                    type: card
                    card:
                      name: Test Test
                      pan: 4716XXXXXXXX1981
                      year: 30
                      cvc: XXX
                      month: 12
                summary: Payment
              '2':
                value:
                  amount: 100
                  currency: KZT
                  description: desc
                  order_id: test_order
                  auto_clearing: false
                  user_id: '1234'
                  from:
                    type: card
                    card:
                      name: Test Test
                      pan: 4400XXXXXXXX4440
                      year: 30
                      cvc: XXX
                      month: 12
                    save: true
                summary: Payment with save
              '3':
                value:
                  amount: 10
                  currency: KZT
                  description: test applepay
                  order_id: apple2
                  auto_clearing: false
                  from:
                    type: tokenized
                    token:
                      type: applepay
                      eci_indicator: '05'
                      online_payment_cryptogram: /wAAAAoAeZvCDJkAAAAAgL1gE4A=
                    card:
                      pan: 4476XXXXXXXX7601
                      month: 12
                      year: 30
                summary: Apple Pay
              '4':
                value:
                  amount: 10
                  currency: KZT
                  description: test googlepay1
                  order_id: '22832'
                  auto_clearing: false
                  from:
                    type: tokenized
                    token:
                      type: googlepay
                      eci_indicator: '07'
                      online_payment_cryptogram: /wAAAAABkQEdJniiHv3JQBAAAAA=
                    card:
                      pan: 4476XXXXXXXX1845
                      month: 12
                      year: 30
                summary: Google Pay
              '5':
                value:
                  amount: 10
                  currency: KZT
                  description: test vts
                  order_id: vts3
                  auto_clearing: false
                  from:
                    type: tokenized
                    token:
                      type: vts
                      eci_indicator: '07'
                      online_payment_cryptogram: /wAAAAAAjiq1vn8AmeRKgwsAAAA=
                    card:
                      pan: 4326XXXXXXXX7667
                      month: 12
                      year: 30
                summary: VTS
              '6':
                value:
                  amount: 10
                  currency: KZT
                  description: test scof
                  order_id: scof
                  auto_clearing: false
                  from:
                    type: tokenized
                    token:
                      type: mscof
                      eci_indicator: '07'
                      online_payment_cryptogram: /wAAAAAAjiq1vn8AmeRKgwsAAAA=
                    card:
                      pan: 4326XXXXXXXX7667
                      month: 12
                      year: 30
                summary: MSCOF
              '7':
                value:
                  amount: 10
                  currency: KZT
                  description: description
                  order_id: '1234'
                  auto_clearing: true
                  from:
                    type: recurrent
                    recurrent:
                      profile_id: 019980ce-543f-71d5-a91f-56bbca52e99e
                summary: Recurrent
              '8':
                value:
                  amount: 100
                  currency: KZT
                  description: desc
                  order_id: test_saved
                  auto_clearing: false
                  user_id: '1234'
                  from:
                    type: saved
                    card:
                      token: d6a069dc-0fac-40d4-be4f-2273350ee256
                summary: Saved
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    examples:
                      - 01978c37-a961-7d20-8434-632242b24d48
                    description: Payment ID (UUID)
                  status:
                    type: string
                    description: Payment status
                    examples:
                      - process
                      - success
                      - error
                  amount:
                    type: number
                    description: Payment amount
                    format: float
                  created_at:
                    type: string
                    examples:
                      - '2025-06-20T07:13:31.068188524Z'
                    description: Payment datetime
                  error:
                    type: object
                    properties:
                      code:
                        type: string
                        examples:
                          - '10045'
                        description: Error code
                      description:
                        type: string
                        examples:
                          - Charge from card declined due to security reasons.
                        description: Error description
                    x-apidog-orders:
                      - code
                      - description
                    description: Object for an error
                required:
                  - id
                  - status
                  - amount
                  - created_at
                x-apidog-orders:
                  - id
                  - status
                  - amount
                  - created_at
                  - error
              examples:
                '1':
                  summary: Status "process"
                  value:
                    id: 01978c37-a961-7d20-8434-632242b24d48
                    status: process
                    amount: 100
                    created_at: '2025-06-20T07:13:31.068188524Z'
                '2':
                  summary: Status "error"
                  value:
                    amount: '100'
                    created_at: '2025-06-19T14:13:49.812118623Z'
                    error:
                      code: '10045'
                      description: Charge from card declined due to security reasons.
                    id: 01978c87-82ad-793f-9a91-eb83d4566410
                    status: error
                '3':
                  summary: Example 1
                  value:
                    error:
                      code: '9403'
                      description: Incorrectly passed input parameters
          headers:
            x-request-id:
              example: ''
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
                examples:
                  - 01978c2b-f191-7b56-92f8-20c7c401d1fc
            x-request-status:
              example: ''
              required: true
              description: Request status.
              schema:
                type: string
                default: success
            x-datetime:
              example: ''
              required: true
              description: Request datetime.
              schema:
                type: string
                examples:
                  - '2025-06-20T07:13:31Z'
          x-apidog-name: OK
        '422':
          description: ''
          content:
            application/json:
              schema:
                title: ''
                type: object
                properties:
                  error:
                    type: object
                    properties:
                      code:
                        type: string
                        description: Error code
                        examples:
                          - '9403'
                      description:
                        type: string
                        description: Error description
                        examples:
                          - Incorrectly passed input parameters
                    x-apidog-orders:
                      - code
                      - description
                    required:
                      - code
                      - description
                x-apidog-orders:
                  - error
                required:
                  - error
          headers:
            x-request-id:
              example: ''
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
                examples:
                  - 01978c50-1436-7b14-b7b6-ed419f9cc06d
            x-request-status:
              example: ''
              required: true
              description: Request status.
              schema:
                type: string
                default: error
            x-datetime:
              example: ''
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: Unprocessable Entity
      security: []
      x-apidog-folder: Gateway API/Async API/create
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587005-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```


# read payment

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/read:
    post:
      summary: read payment
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/read
      parameters:
        - name: Accept
          in: header
          description: >-
            Indicates the media types that the client is able to understand from
            the server response.
          required: true
          example: ''
          schema:
            type: string
            default: application/json
        - name: Content-Type
          in: header
          description: Specifies the media type of the resource being sent to the server.
          required: true
          example: ''
          schema:
            type: string
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: ''
          schema:
            type: string
            examples:
              - >-
                eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
        - name: X-Action
          in: header
          description: >-
            Invoked method.

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.payment.status
        - name: X-Request-Id
          in: header
          description: Unique request ID (UUID).
          required: true
          example: ''
          schema:
            type: string
            examples:
              - 01978cb8-60f4-7b04-8b8d-8075a11d56a3
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:
                  type: string
                  title: "Required if \"order_id\" is not provided\t"
                  description: Payment ID (UUID).
                  examples:
                    - 01978c2f-79bc-72de-85f1-2ca183462dc5
                order_id:
                  type: string
                  title: Required if "id" is not provided
                  examples:
                    - '12345'
                  description: Order number in the merchant's system.
              x-apidog-orders:
                - id
                - order_id
              required:
                - id
            example:
              id: 01907dac-a93d-776e-b475-cba6a54a4888
              order_id: '1234'
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    description: Unique identifier of the payment generated by the gateway.
                    examples:
                      - 01978d0e-b956-7ea2-9a42-32cff1f44ede
                    format: uuid
                  order_id:
                    type: string
                    description: >-
                      Merchant’s order reference that links the payment to the
                      merchant system.
                    examples:
                      - '12345'
                    format: char
                  parent_id:
                    type: string
                    description: UUID of the parent payment
                    examples:
                      - 01978d27-fdb1-7fd1-8812-ce7a83414c72
                    format: uuid
                  status:
                    type: string
                    description: >-
                      Current processing state of the payment (approved,
                      success, error, etc.).
                    examples:
                      - process
                      - success
                      - approved
                      - reversed
                      - error
                    format: char
                  amount:
                    type: number
                    description: >-
                      Transaction amount in the original currency units (e.g.,
                      “103” = 103 KZT).
                    examples:
                      - 100
                    format: float
                  created_at:
                    type: string
                    description: ' Timestamp when the payment record was created on the gateway.'
                    examples:
                      - '2025-06-20T07:13:31.068188524Z'
                    format: date-time
                  3ds:
                    type: object
                    properties:
                      flow_type:
                        type: string
                        description: Details of 3DS flow used (Challenge or Frictionless).
                        examples:
                          - F
                          - C
                      acs_url:
                        type: string
                        description: >-
                          URL to which the client should be redirected via POST.
                          The request body must include the parameter TermUrl,
                          which is the URL the client will be returned to after
                          3DS completion.
                        examples:
                          - https://acs.com/something
                    required:
                      - flow_type
                      - acs_url
                    x-apidog-orders:
                      - flow_type
                      - acs_url
                    description: >-
                      Object containing information for the client’s 3DS
                      authentication.
                  from:
                    type: object
                    properties:
                      recurrent:
                        type: object
                        properties:
                          profile_id:
                            type: string
                            description: Recurrent profile ID
                          profile_expiry_date:
                            type: string
                            description: Recurrent profile expiration date
                        x-apidog-orders:
                          - profile_id
                          - profile_expiry_date
                        required:
                          - profile_id
                          - profile_expiry_date
                      card:
                        type: object
                        properties:
                          token:
                            type: string
                            description: >-
                              Unique identifier of the saved card in our Freedom
                              Pay Card-on-File storage. This value is the same
                              identifier that should be used as from.card.uuid
                              in subsequent payments with a saved card.
                            examples:
                              - 01978d11-669e-7dd1-bf1b-75a12bf57ca9
                          brand:
                            type: string
                        x-apidog-orders:
                          - token
                          - brand
                        required:
                          - brand
                          - token
                        description: Card token
                    x-apidog-orders:
                      - recurrent
                      - card
                  clearing:
                    type: object
                    properties:
                      cleared:
                        type: boolean
                        description: Payment clearing status
                      amount:
                        type: number
                        format: float
                        examples:
                          - 100
                        description: Amount cleared
                    required:
                      - cleared
                      - amount
                    x-apidog-orders:
                      - cleared
                      - amount
                  additional:
                    type: object
                    properties:
                      approval_code:
                        type: string
                        description: Payment approval code sent by the issuing bank
                      reference:
                        type: string
                        description: >-
                          Unique bank transaction identifier assigned by the
                          bank (RRN)
                      intreference:
                        type: string
                        description: >-
                          Unique bank transaction internal identifier assigned
                          by the bank
                    x-apidog-orders:
                      - approval_code
                      - reference
                      - intreference
                    required:
                      - approval_code
                      - reference
                      - intreference
                  refund_payments:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: UUID of the refund payment
                        amount:
                          type: integer
                          description: Amount of the refund payment
                        status:
                          type: string
                          description: Status of the refund payment
                      required:
                        - id
                        - amount
                        - status
                      x-apidog-orders:
                        - id
                        - amount
                        - status
                    description: Array containing information about refund payments
                  reverse_payments:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: UUID of the reversed payment
                        amount:
                          type: integer
                          description: Amount of the reversed payment
                        status:
                          type: string
                          description: Status of the reversed payment
                      x-apidog-orders:
                        - id
                        - amount
                        - status
                      required:
                        - id
                        - amount
                        - status
                    description: >-
                      Array containing information about reversed (canceled)
                      payments
                required:
                  - id
                  - order_id
                  - parent_id
                  - status
                  - amount
                  - created_at
                  - 3ds
                  - from
                  - clearing
                x-apidog-orders:
                  - id
                  - order_id
                  - parent_id
                  - status
                  - amount
                  - created_at
                  - 3ds
                  - from
                  - clearing
                  - additional
                  - refund_payments
                  - reverse_payments
              examples:
                '1':
                  summary: Status "approved"
                  value:
                    id: 01978d0e-b956-7ea2-9a42-32cff1f44ede
                    status: approved
                    amount: 100
                    created_at: '2025-06-20T07:13:31.068188524Z'
                    order_id: '1234'
                    clearing:
                      cleared: false
                      amount: 0
                    from:
                      card:
                        token: 01978d11-669e-7dd1-bf1b-75a12bf57ca9
                        brand: VI
                    additional:
                      approval_code: 95F69T
                      reference: '1234567891234'
                      intreference: AC1BFED11052BFAC
                    3ds:
                      acs_url: ''
                      flow_type: F
                '2':
                  summary: Status "process"
                  value:
                    id: 01978d0e-b956-7ea2-9a42-32cff1f44ede
                    status: process
                    amount: 100
                    created_at: '2025-06-20T07:13:31.068188524Z'
                    order_id: '1234'
                    from:
                      card:
                        brand: VI
                        token: 01978d11-669e-7dd1-bf1b-75a12bf57ca9
                    3ds:
                      acs_url: ''
                '3':
                  summary: Status "success"
                  value:
                    id: 01978d0e-b956-7ea2-9a42-32cff1f44ede
                    status: success
                    amount: 100
                    created_at: '2025-06-20T07:13:31.068188524Z'
                    order_id: '1234'
                    clearing:
                      cleared: true
                      amount: 100
                    from:
                      card:
                        token: 01978d11-669e-7dd1-bf1b-75a12bf57ca9
                        brand: VI
                    refund_payments:
                      - id: 01978d53-4748-74c1-9c0a-0ca2b64b9c1b
                        amount: -100
                        status: success
                    additional:
                      approval_code: 95F69T
                      reference: '1234567891234'
                      intreference: AC1BFED11052BFAC
                    3ds:
                      acs_url: ''
                      flow_type: F
                '4':
                  summary: Status "reversed"
                  value:
                    id: 01978d55-748b-79a4-9e9e-77ab3c15aadd
                    status: reversed
                    amount: 100
                    created_at: '2025-06-20T12:34:37.323632498Z'
                    order_id: '1234'
                    clearing:
                      cleared: false
                      amount: 0
                    from:
                      card:
                        token: 01978d27-fdb1-7fd1-8812-ce7a83414c72
                        brand: VI
                    reverse_payments:
                      - id: 01978d55-ba15-738e-8a99-44cd25f0eb6b
                        amount: -100
                        status: success
                    additional:
                      approval_code: '218881'
                      reference: '517101387057'
                      intreference: 8A24B87C6A5D27D9
                    3ds:
                      acs_url: ''
                      flow_type: F
                '5':
                  summary: Status "error"
                  value:
                    amount: '100'
                    created_at: '2025-06-19T14:13:49.812118623Z'
                    error:
                      code: '10012'
                      description: Limits on your card
                    id: 01978c87-82ad-793f-9a91-eb83d4566410
                    status: error
                '6':
                  summary: Status "waiting_3ds"
                  value:
                    id: 0199765b-a007-7339-93fe-f073ac14aa9b
                    status: waiting_3ds
                    amount: 10
                    created_at: '2025-09-23T11:35:40.295211818Z'
                    order_id: order064
                    from:
                      card:
                        token: d9118161-8840-44e6-9cfa-91496c6bd653
                        brand: VI
                    3ds:
                      acs_url: >-
                        https://secure-pg.freedompay.kz/v2/user/3ds-page/e3a549b9-6a09-4f38-ba7c-b8723f4181a4
                      flow_type: C
                '7':
                  summary: Empty response body
                  value: {}
          headers:
            x-request-id:
              example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
            x-request-status:
              example: success
              required: true
              description: Request status.
              schema:
                type: string
            x-datetime:
              example: '2025-06-20T07:13:31Z'
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Async API/read
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587007-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# read request

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/read:
    post:
      summary: read request
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/read
      parameters:
        - name: Accept
          in: header
          description: >
            Indicates the media types that the client is able to understand from
            the server response.
          required: true
          example: application/json
          schema:
            type: string
        - name: Content-Type
          in: header
          description: |
            Specifies the media type of the resource being sent to the server.
          required: true
          example: application/json
          schema:
            type: string
        - name: X-Action
          in: header
          description: Invoked method.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.request.status
        - name: X-Request-Id
          in: header
          description: >-
            Unique request ID (UUID).

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
          schema:
            type: string
            format: uuid
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: >-
            eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:
                  type: string
                  description: >-
                    The "id" sent in the request body corresponds to the
                    "x-request-id" value from response headers.
              required:
                - id
              x-apidog-orders:
                - id
            example:
              id: 29e0f9f5-592d-46f5-8eb0-6aad0f44c28c
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  status:
                    type: string
                  response:
                    type: object
                    properties:
                      id:
                        type: string
                      status:
                        type: string
                      amount:
                        type: integer
                      created_at:
                        type: string
                    required:
                      - id
                      - status
                      - amount
                      - created_at
                    x-apidog-orders:
                      - id
                      - status
                      - amount
                      - created_at
                required:
                  - id
                  - status
                  - response
                x-apidog-orders:
                  - id
                  - status
                  - response
              examples:
                '1':
                  summary: Status "approved"
                  value:
                    id: 23fce447-82ad-45df-be37-a67151e2e299
                    status: success
                    response:
                      id: 01978d5c-ab89-72a0-a5a1-2cc56029f041
                      status: approved
                      amount: 40
                      created_at: '2025-06-20T12:42:30.15317269Z'
                '2':
                  summary: Status "process"
                  value:
                    id: d0708790-85fa-4e49-9151-3ff2a6e9b855
                    status: success
                    response:
                      id: ee648c34-a6b0-4a26-afd7-819198aae664
                      status: process
                      amount: 100.01
                      created_at: '2005-08-09T18:31:42+06:00'
                '3':
                  summary: Status "error"
                  value:
                    id: bfe49b6e-2af3-4da8-aef3-c609ed1be949
                    status: error
                    response:
                      id: bfe49b6e-2af3-4da8-aef3-c609ed1be949
                      status: error
                      amount: 0
                      created_at: '0001-01-01T00:00:00Z'
                      error:
                        code: '1202'
                        description: Incorrect payment id
                '4':
                  summary: Status "success"
                  value:
                    id: 23fce447-82ad-45df-be37-a67151e2e299
                    status: success
                    response:
                      id: 01978d5c-ab89-72a0-a5a1-2cc56029f041
                      status: success
                      amount: 40
                      created_at: '2025-06-20T12:42:30.15317269Z'
          headers:
            x-request-id:
              example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
            x-request-status:
              example: success
              required: true
              description: Request status.
              schema:
                type: string
            x-datetime:
              example: '2025-06-20T07:13:31Z'
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Async API/read
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587008-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# read request

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/read:
    post:
      summary: read request
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/read
      parameters:
        - name: Accept
          in: header
          description: >
            Indicates the media types that the client is able to understand from
            the server response.
          required: true
          example: application/json
          schema:
            type: string
        - name: Content-Type
          in: header
          description: |
            Specifies the media type of the resource being sent to the server.
          required: true
          example: application/json
          schema:
            type: string
        - name: X-Action
          in: header
          description: Invoked method.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.request.status
        - name: X-Request-Id
          in: header
          description: >-
            Unique request ID (UUID).

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
          schema:
            type: string
            format: uuid
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: >-
            eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:
                  type: string
                  description: >-
                    The "id" sent in the request body corresponds to the
                    "x-request-id" value from response headers.
              required:
                - id
              x-apidog-orders:
                - id
            example:
              id: 29e0f9f5-592d-46f5-8eb0-6aad0f44c28c
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  status:
                    type: string
                  response:
                    type: object
                    properties:
                      id:
                        type: string
                      status:
                        type: string
                      amount:
                        type: integer
                      created_at:
                        type: string
                    required:
                      - id
                      - status
                      - amount
                      - created_at
                    x-apidog-orders:
                      - id
                      - status
                      - amount
                      - created_at
                required:
                  - id
                  - status
                  - response
                x-apidog-orders:
                  - id
                  - status
                  - response
              examples:
                '1':
                  summary: Status "approved"
                  value:
                    id: 23fce447-82ad-45df-be37-a67151e2e299
                    status: success
                    response:
                      id: 01978d5c-ab89-72a0-a5a1-2cc56029f041
                      status: approved
                      amount: 40
                      created_at: '2025-06-20T12:42:30.15317269Z'
                '2':
                  summary: Status "process"
                  value:
                    id: d0708790-85fa-4e49-9151-3ff2a6e9b855
                    status: success
                    response:
                      id: ee648c34-a6b0-4a26-afd7-819198aae664
                      status: process
                      amount: 100.01
                      created_at: '2005-08-09T18:31:42+06:00'
                '3':
                  summary: Status "error"
                  value:
                    id: bfe49b6e-2af3-4da8-aef3-c609ed1be949
                    status: error
                    response:
                      id: bfe49b6e-2af3-4da8-aef3-c609ed1be949
                      status: error
                      amount: 0
                      created_at: '0001-01-01T00:00:00Z'
                      error:
                        code: '1202'
                        description: Incorrect payment id
                '4':
                  summary: Status "success"
                  value:
                    id: 23fce447-82ad-45df-be37-a67151e2e299
                    status: success
                    response:
                      id: 01978d5c-ab89-72a0-a5a1-2cc56029f041
                      status: success
                      amount: 40
                      created_at: '2025-06-20T12:42:30.15317269Z'
          headers:
            x-request-id:
              example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
            x-request-status:
              example: success
              required: true
              description: Request status.
              schema:
                type: string
            x-datetime:
              example: '2025-06-20T07:13:31Z'
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: OK
      security: []
      x-apidog-folder: Gateway API/Async API/read
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587008-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# edit payment.refund

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/edit:
    post:
      summary: edit payment.refund
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/edit
      parameters:
        - name: Accept
          in: header
          description: >-
            Indicates the media types that the client is able to understand from
            the server response.
          required: false
          example: application/json
          schema:
            type: string
        - name: Content-Type
          in: header
          description: Specifies the media type of the resource being sent to the server.
          required: false
          example: application/json
          schema:
            type: string
        - name: X-Action
          in: header
          description: Invoked method.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.payment.refund
        - name: X-Request-Id
          in: header
          description: >-
            Unique request ID (UUID).

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
          schema:
            type: string
            format: uuid
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: >-
            eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:
                  type: string
                  format: uuid
                  description: Payment ID (UUID).
                amount:
                  type: number
                  format: float
                  description: Payment amount.
              required:
                - id
                - amount
              x-apidog-orders:
                - id
                - amount
            example:
              id: 01904e28-a01d-75d0-bc3a-56d777f0a39b
              amount: 100
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  amount:
                    type: integer
                  refund_payment:
                    type: object
                    properties:
                      id:
                        type: string
                      status:
                        type: string
                      amount:
                        type: integer
                    required:
                      - id
                      - status
                      - amount
                    x-apidog-orders:
                      - id
                      - status
                      - amount
                required:
                  - id
                  - amount
                  - refund_payment
                x-apidog-orders:
                  - id
                  - amount
                  - refund_payment
              example:
                id: 01978d4f-fb27-7615-a95c-d646dc1df3f3
                amount: 100
                refund_payment:
                  id: 01978d53-4748-74c1-9c0a-0ca2b64b9c1b
                  status: process
                  amount: -100
          headers:
            x-request-id:
              example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
            x-request-status:
              example: success
              required: true
              description: Request status.
              schema:
                type: string
            x-datetime:
              example: '2025-06-20T07:13:31Z'
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Async API/edit
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587009-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# edit payment.reverse

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/edit:
    post:
      summary: edit payment.reverse
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/edit
      parameters:
        - name: Accept
          in: header
          description: >-
            Indicates the media types that the client is able to understand from
            the server response.
          required: true
          example: application/json
          schema:
            type: string
        - name: Content-Type
          in: header
          description: Specifies the media type of the resource being sent to the server.
          required: true
          example: application/json
          schema:
            type: string
        - name: X-Action
          in: header
          description: Invoked method.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.payment.reverse
        - name: X-Request-Id
          in: header
          description: >-
            Unique request ID (UUID).

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
          schema:
            type: string
            format: uuid
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: >-
            eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:
                  type: string
                  description: Payment ID (UUID).
              required:
                - id
              x-apidog-orders:
                - id
            example:
              id: 01909b30-b86a-77ef-ab25-0a7d126e8f4a
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  amount:
                    type: integer
                  reverse_payment:
                    type: object
                    properties:
                      id:
                        type: string
                      status:
                        type: string
                    required:
                      - id
                      - status
                    x-apidog-orders:
                      - id
                      - status
                required:
                  - id
                  - amount
                  - reverse_payment
                x-apidog-orders:
                  - id
                  - amount
                  - reverse_payment
              example:
                id: 01978d5c-ab89-72a0-a5a1-2cc56029f041
                amount: 100
                reverse_payment:
                  id: 01978d62-9962-7380-b51a-67c174e4b4f6
                  status: process
          headers:
            x-request-id:
              example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
            x-request-status:
              example: success
              required: true
              description: Request status.
              schema:
                type: string
            x-datetime:
              example: '2025-06-20T07:13:31Z'
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Async API/edit
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587010-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```

# edit payment.clearing

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /v5/g2g/edit:
    post:
      summary: edit payment.clearing
      deprecated: false
      description: ''
      tags:
        - Gateway API/Async API/edit
      parameters:
        - name: Accept
          in: header
          description: >-
            Indicates the media types that the client is able to understand from
            the server response.
          required: true
          example: application/json
          schema:
            type: string
        - name: Content-Type
          in: header
          description: Specifies the media type of the resource being sent to the server.
          required: true
          example: application/json
          schema:
            type: string
        - name: X-Action
          in: header
          description: Invoked method.
          required: true
          example: ''
          schema:
            type: string
            default: gateway.payment.clearing
        - name: X-Request-Id
          in: header
          description: >-
            Unique request ID (UUID).

            If the same request_id is sent more than once, the API guarantees
            idempotent behavior and returns the original response.
          required: true
          example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
          schema:
            type: string
            format: uuid
        - name: X-JWS-Signature
          in: header
          description: Request signature.
          required: true
          example: >-
            eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1NiJ9.eyJpc3MiOiJleGFtcGxlLmNvbSIsInN1YiI6InVzZXIxMjMiLCJhdWQiOiJhcGkuZXhhbXBsZS5jb20iLCJleHAiOjE2MzAwMDAwMDAsImlhdCI6MTYyOTk5NjQwMH0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                id:
                  type: string
                  format: uuid
                  examples:
                    - 01978d27-fdb1-7fd1-8812-ce7a83414c72
                  description: Payment ID (UUID).
                amount:
                  type: number
                  format: float
                  examples:
                    - 100
                  description: Clearing amount.
              required:
                - id
                - amount
              x-apidog-orders:
                - id
                - amount
            example:
              id: 019052f1-e8dd-7de5-b09c-787d09f53891
              amount: 100
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  status:
                    type: string
                  amount:
                    type: integer
                  created_at:
                    type: string
                  clearing:
                    type: object
                    properties:
                      amount:
                        type: integer
                    required:
                      - amount
                    x-apidog-orders:
                      - amount
                required:
                  - id
                  - status
                  - amount
                  - created_at
                  - clearing
                x-apidog-orders:
                  - id
                  - status
                  - amount
                  - created_at
                  - clearing
              example:
                id: 01976974-b5ec-7e89-bb88-5ba118385e88
                status: process_clearing
                amount: 100
                created_at: '2025-06-13T13:22:25.900953117Z'
                clearing:
                  amount: 0
          headers:
            x-request-id:
              example: 01978c2b-f191-7b56-92f8-20c7c401d1fc
              required: true
              description: Request ID (UUID), equals X-Request-Id from request headers.
              schema:
                type: string
            x-request-status:
              example: success
              required: true
              description: Request status.
              schema:
                type: string
            x-datetime:
              example: '2025-06-20T07:13:31Z'
              required: true
              description: Request datetime.
              schema:
                type: string
          x-apidog-name: Success
      security: []
      x-apidog-folder: Gateway API/Async API/edit
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/640842/apis/api-9587011-run
components:
  schemas: {}
  securitySchemes:
    card-api:
      type: jwt
      scheme: bearer
      bearerFormat: JWT
      x-apidog:
        addTokenTo: header
        headerPrefix: Bearer
servers:
  - url: https://api.freedompay.kz
    description: KZ
  - url: https://api.freedompay.uz
    description: UZ
  - url: https://api.freedompay.kg
    description: KG
security: []

```


