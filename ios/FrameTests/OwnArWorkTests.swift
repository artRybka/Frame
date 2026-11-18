import CoreGraphics
import simd
import XCTest
@testable import Frame

/// The work pinned in the room by the phone's AR session after the first
/// photograph of a scan (Mateusz 2026-11-18 08:22 UTC: "A może aparat w AR
/// mógłby dodawać po pierwszym kroku jakieś znaczniki wkoło obrazu?").
/// The session itself runs only on a phone; what it counts is here.
final class OwnArWorkTests: XCTestCase {
    /// A work 60 cm wide and 80 cm tall on a wall that faces +z, its
    /// middle 1.5 m up, and the phone 1.2 m before it.
    private let corners: [SIMD3<Float>] = [
        SIMD3(-0.3, 1.9, 0), SIMD3(0.3, 1.9, 0), SIMD3(0.3, 1.1, 0), SIMD3(-0.3, 1.1, 0),
    ]
    private let eye = SIMD3<Float>(0, 1.5, 1.2)

    func testThePhonesPlaceIsTheAngleToTheSide() throws {
        let work = try XCTUnwrap(OwnArWork(corners: corners, from: eye))
        XCTAssertEqual(work.angle(from: eye), 0, accuracy: 0.01)
        XCTAssertEqual(work.away(from: eye), 1, accuracy: 0.001)
        XCTAssertEqual(work.normal.z, 1, accuracy: 1e-5)
        XCTAssertEqual(work.right.x, 1, accuracy: 1e-5)
        // 30° to its left and to its right, as far away: negative from the left.
        let left = SIMD3<Float>(-0.6, 1.5, 1.0392)
        XCTAssertEqual(work.angle(from: left), -30, accuracy: 0.05)
        XCTAssertEqual(work.away(from: left), 1, accuracy: 0.001)
        XCTAssertEqual(work.angle(from: SIMD3(0.6, 1.5, 1.0392)), 30, accuracy: 0.05)
        // Held higher or lower, the phone stands as far to the side.
        XCTAssertEqual(work.angle(from: SIMD3(-0.6, 1.0, 1.0392)), -30, accuracy: 0.05)
        // A step back is farther, not more to the side.
        XCTAssertEqual(work.angle(from: SIMD3(-1.2, 1.5, 2.0784)), -30, accuracy: 0.05)
        XCTAssertEqual(work.away(from: SIMD3(-1.2, 1.5, 2.0784)), 2, accuracy: 0.001)
        // The same angles as the scan asks for.
        XCTAssertTrue(OwnScanView.near.contains(abs(work.angle(from: left))))
        XCTAssertEqual(
            OwnScanView.side(target: -OwnScanView.side, angle: work.angle(from: left), away: work.away(from: left)), .hold
        )
    }

    func testTheWorkFacesThePhoneHoweverItsCornersCome() throws {
        // Pinned from the other side of the room: its right is the other way.
        let behind = SIMD3<Float>(0, 1.5, -1.2)
        let turned = [corners[1], corners[0], corners[3], corners[2]]
        let work = try XCTUnwrap(OwnArWork(corners: turned, from: behind))
        XCTAssertEqual(work.normal.z, -1, accuracy: 1e-5)
        XCTAssertEqual(work.right.x, -1, accuracy: 1e-5)
        XCTAssertEqual(work.angle(from: SIMD3(0.6, 1.5, -1.0392)), -30, accuracy: 0.05)
        // A work lying on a table, the phone over it.
        let table: [SIMD3<Float>] = [SIMD3(-0.2, 0.7, -0.3), SIMD3(0.2, 0.7, -0.3), SIMD3(0.2, 0.7, 0.3), SIMD3(-0.2, 0.7, 0.3)]
        let over = try XCTUnwrap(OwnArWork(corners: table, from: SIMD3(0, 1.3, 0)))
        XCTAssertEqual(over.normal.y, 1, accuracy: 1e-5)
        XCTAssertEqual(over.angle(from: SIMD3(-0.3, 1.2196, 0)), -30, accuracy: 0.05)
    }

    func testWhatIsNotAWorkIsNotPinned() {
        XCTAssertNil(OwnArWork(corners: Array(corners.prefix(3)), from: eye))
        // Seen edge-on, too near, too far, or a speck.
        XCTAssertNil(OwnArWork(corners: corners, from: SIMD3(1.2, 1.5, 0.05)))
        XCTAssertNil(OwnArWork(corners: corners, from: SIMD3(0, 1.5, 0.05)))
        XCTAssertNil(OwnArWork(corners: corners, from: SIMD3(0, 1.5, 12)))
        let speck = corners.map { SIMD3<Float>($0.x * 0.02, 1.5 + ($0.y - 1.5) * 0.02, 0) }
        XCTAssertNil(OwnArWork(corners: speck, from: eye))
    }

    func testTheWallIsFeltWithinTheOutlineAndItsCornersLieOnIt() throws {
        let outline = [CGPoint(x: 0.2, y: 0.1), CGPoint(x: 0.8, y: 0.1), CGPoint(x: 0.8, y: 0.9), CGPoint(x: 0.2, y: 0.9)]
        let felt = OwnArWork.felt(outline)
        XCTAssertEqual(felt[0].x, 0.32, accuracy: 1e-9)
        XCTAssertEqual(felt[0].y, 0.26, accuracy: 1e-9)
        XCTAssertEqual(felt[2].x, 0.68, accuracy: 1e-9)
        XCTAssertEqual(felt[2].y, 0.74, accuracy: 1e-9)
        // The sensor lies on its side: the screen's top left is its bottom
        // left, the screen's top right its top left.
        XCTAssertEqual(OwnArWork.sensor(CGPoint(x: 0, y: 0)), CGPoint(x: 0, y: 1))
        XCTAssertEqual(OwnArWork.sensor(CGPoint(x: 1, y: 0)), CGPoint(x: 0, y: 0))
        XCTAssertEqual(OwnArWork.sensor(CGPoint(x: 1, y: 1)), CGPoint(x: 1, y: 0))

        // Four places on the work give its plane; one of them on the wall
        // a hand's width behind does not.
        let hits = corners.map { SIMD3<Float>($0.x * 0.6, 1.5 + ($0.y - 1.5) * 0.6, 0.01) }
        let plane = try XCTUnwrap(OwnArWork.plane(through: hits))
        XCTAssertEqual(abs(plane.normal.z), 1, accuracy: 1e-5)
        XCTAssertEqual(plane.point.z, 0.01, accuracy: 1e-6)
        var off = hits
        off[1].z -= 0.3
        XCTAssertNil(OwnArWork.plane(through: off))
        // A corner's ray from the phone meets the plane at the corner.
        let goal = SIMD3<Float>(0.3, 1.9, 0.01)
        let at = try XCTUnwrap(OwnArWork.hit(origin: eye, direction: simd_normalize(goal - eye), plane: plane))
        XCTAssertEqual(simd_length(at - goal), 0, accuracy: 1e-4)
        // Looking away from the wall, or along it: nothing.
        XCTAssertNil(OwnArWork.hit(origin: eye, direction: SIMD3(0, 0, 1), plane: plane))
        XCTAssertNil(OwnArWork.hit(origin: eye, direction: SIMD3(1, 0, 0), plane: plane))
    }

    func testTheArPhotographStandsAsThePhoneIsHeld() {
        XCTAssertEqual(OwnArSession.turn(0), OwnCameraSession.orientation(90))
        XCTAssertEqual(OwnArSession.turn(1), OwnCameraSession.orientation(0))
        XCTAssertEqual(OwnArSession.turn(-1), OwnCameraSession.orientation(180))
    }
}
