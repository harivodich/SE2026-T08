# Kiểm tra hồ sơ thiết kế

Ngày: 04/10/2026.

- 10 tài liệu Markdown; 10 nguồn UML và 10 SVG được render cục bộ.
- 4 JSON Schema parse được; mọi $ref nội bộ được resolve.
- 15 positive/negative contract checks pass trên keywords sử dụng. Validator này không phải compiler JSON Schema chuẩn đầy đủ.
- 19 liên kết file nội bộ tồn tại.
- XML parser đọc thành công cả 10 SVG; đã kiểm tra trực quan bản raster của 10 góc nhìn và sửa nhãn/đường nối bị chồng ở activity/state views.
- JavaScript nhúng trong HTML vượt kiểm tra cú pháp; chưa kiểm hành vi tương tác bằng trình duyệt.
- Renderer cảnh báo font cache không writable; ảnh vẫn render thành công và dấu tiếng Việt được kiểm tra trực quan.
- PlantUML compiler không có trong PATH: chưa compile .puml bằng PlantUML.
- Chưa chạy browser QA hoặc benchmark/train/app tests; không có app implementation trong task này.

SVG là bản trình bày từ canonical diagram model, không phải output của PlantUML compiler. Graph views dùng Graphviz WASM; sequence và activity views dùng SVG lifelines/swimlanes.
